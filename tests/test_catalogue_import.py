import csv
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse

from muqola.catalogue.importer import COLUMNS, IMPORT_EMAIL
from muqola.catalogue.models import Game
from muqola.catalogue.services import search, write_game
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from tests.helpers import member

pytestmark = pytest.mark.django_db


def source(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"title": "Jeu fictif", "external_source": "synthetic", **row})
    return path


def run(path: Path, dry_run: bool = False) -> dict[str, int]:
    output = StringIO()
    call_command("import_games", str(path), dry_run=dry_run, stdout=output, stderr=StringIO())
    return json.loads(output.getvalue())  # type: ignore[no-any-return]


def test_import_is_persistent_idempotent_and_never_creates_copies(tmp_path: Path) -> None:
    path = source(
        tmp_path, [{"external_id": "1", "title": " Câtan   FICTIF "}, {"external_id": "2"}]
    )
    with patch("socket.create_connection", side_effect=AssertionError("Réseau interdit")):
        assert run(path)["created"] == 2
        result = run(path)
    assert result == {"created": 0, "existing": 2, "ignored": 0, "invalid": 0, "dry_run": False}
    game = Game.objects.get(external_id="1")
    assert game.title_key == "catan fictif" and game.year is None and game.publisher == ""
    assert game.external_source == "synthetic"
    assert not OwnedGame.objects.exists()
    account = User.objects.get(email=IMPORT_EMAIL)
    assert game.created_by == account
    assert not account.is_active and not account.is_staff and not account.is_superuser
    assert account.email_verified_at is None and not account.has_usable_password()
    path.unlink()
    assert search(member()).count() == 2


def test_import_preserves_existing_hidden_fiche_and_handles_duplicates(tmp_path: Path) -> None:
    game = write_game(member(), {"title": "Ne pas remplacer"})
    game.external_source, game.external_id, game.hidden = "synthetic", "1", True
    game.save()
    before = Game.objects.values().get(pk=game.pk)
    result = run(
        source(tmp_path, [{"external_id": "1"}, {"external_id": "2"}, {"external_id": "2"}])
    )
    assert result["created"] == 1 and result["existing"] == 2
    assert Game.objects.values().get(pk=game.pk) == before


@pytest.mark.parametrize("dry_run", [False, True])
def test_invalid_rows_do_not_prevent_valid_rows(tmp_path: Path, dry_run: bool) -> None:
    path = source(
        tmp_path,
        [
            {"external_id": "valid"},
            {"external_id": "long", "title": "x" * 121},
            {"external_id": "number", "year": "oops"},
            {"external_id": "range", "year": "2201"},
            {"external_id": "order", "players_min": "5", "players_max": "2"},
            {"external_id": "description", "description": "x" * 2001},
            {"external_id": "publisher", "publisher": "x" * 121},
            {"external_id": "", "external_source": ""},
            {"external_id": "", "external_source": "synthetic"},
            {"external_id": "valid2", "players_min": "2", "players_max": "4", "duration": "30"},
        ],
    )
    result = run(path, dry_run)
    assert result["created"] == 2 and result["invalid"] == 7 and result["ignored"] == 1
    assert Game.objects.count() == (0 if dry_run else 2)
    assert User.objects.count() == (0 if dry_run else 1)


def test_dry_run_has_no_writes_and_counts_in_file_duplicates(tmp_path: Path) -> None:
    path = source(tmp_path, [{"external_id": "1"}, {"external_id": "1"}])
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        result = run(path, True)
    assert result["created"] == 1 and result["existing"] == 1
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert not Game.objects.exists() and not User.objects.exists()


def test_batches_and_missing_values(tmp_path: Path) -> None:
    path = source(tmp_path, [{"external_id": str(i)} for i in range(5)])
    with patch("muqola.catalogue.importer.BATCH_SIZE", 2):
        assert run(path)["created"] == 5
    assert Game.objects.count() == 5


@pytest.mark.parametrize("content", ["title,year\nJeu,2020\n", "title,title\nA,B\n", ""])
def test_invalid_headers_fail_without_writes(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(CommandError, match="En-tête"):
        run(path)
    assert not User.objects.exists() and not Game.objects.exists()


def test_short_and_extra_rows_are_invalid(tmp_path: Path) -> None:
    path = source(tmp_path, [])
    with path.open("a") as stream:
        stream.write("short,row\n" + ",".join(["extra"] * 10) + "\n")
    assert run(path)["invalid"] == 2
    assert not Game.objects.exists()


def test_reserved_account_collision_is_not_modified(tmp_path: Path) -> None:
    human = User.objects.create_user(
        email=IMPORT_EMAIL, password="Fictif-12345", display_name="Humain"
    )
    with pytest.raises(CommandError, match="compte technique"):
        run(source(tmp_path, [{"external_id": "1"}]))
    human.refresh_from_db()
    assert human.is_active and human.has_usable_password() and not Game.objects.exists()


def test_technical_account_cannot_log_in_or_access_business(tmp_path: Path, client: Client) -> None:
    run(source(tmp_path, [{"external_id": "1"}]))
    user = User.objects.get(email=IMPORT_EMAIL)
    assert not client.login(email=IMPORT_EMAIL, password="!")
    client.force_login(user)
    response = client.get(reverse("catalogue:index"))
    assert response.status_code in {302, 403}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("external_source", "x" * 81),
        ("external_id", "x" * 121),
        ("players_min", "0"),
        ("players_max", "101"),
        ("duration", "-1"),
        ("duration", "10001"),
        ("description", "Texte\x00invalide"),
    ],
)
def test_model_field_limits(tmp_path: Path, field: str, value: str) -> None:
    result = run(source(tmp_path, [{"external_id": "1", field: value}]))
    assert result["invalid"] == 1 and result["created"] == 0
    assert not Game.objects.exists() and not User.objects.exists()


def test_failed_batch_rolls_back_without_losing_previous_batch(tmp_path: Path) -> None:
    from django.db import IntegrityError

    path = source(tmp_path, [{"external_id": str(i)} for i in range(4)])
    original = Game.save

    def fail(self: Game, *args: object, **kwargs: object) -> None:
        if self.external_id == "3":
            raise IntegrityError("Panne synthétique")
        original(self, *args, **kwargs)

    with patch("muqola.catalogue.importer.BATCH_SIZE", 2), patch.object(Game, "save", fail):
        with pytest.raises(CommandError, match="Import interrompu"):
            run(path)
    assert set(Game.objects.values_list("external_id", flat=True)) == {"0", "1"}
    assert run(path)["created"] == 2


def test_utf8_bom_and_invalid_encoding(tmp_path: Path) -> None:
    path = source(tmp_path, [{"external_id": "1", "description": "Ligne 1\nLigne 2"}])
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert run(path)["created"] == 1
    path.write_bytes(b"\xff")
    with pytest.raises(CommandError):
        run(path)
    assert Game.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_imports_do_not_overwrite_or_duplicate(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    path = source(tmp_path, [{"external_id": str(i)} for i in range(4)])
    barrier = Barrier(2)

    def import_once(_: int) -> dict[str, int]:
        try:
            barrier.wait(timeout=10)
            return run(path)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(import_once, range(2)))
    assert sum(result["created"] for result in results) == 4
    assert sum(result["existing"] for result in results) == 4
    assert Game.objects.count() == 4 and User.objects.count() == 1
