import csv
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from muqola.catalogue.importer import IMPORT_EMAIL
from muqola.catalogue.models import Game, GameAlias, GameIllustration
from muqola.catalogue.services import search, write_game
from muqola.catalogue.wikidata_importer import COLUMNS
from muqola.communities import services as communities
from muqola.communities.models import Membership
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from muqola.inventory.services import add_to_collection
from tests.helpers import member

pytestmark = pytest.mark.django_db


def source(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "wikidata_id": "Q900000001",
                    "title_fr": "Le Chemin fictif",
                    "title_en": "Fictional Trail",
                    "data_source": "Wikidata",
                    "data_license": "CC0",
                    "image_review_status": "no_image",
                    **row,
                }
            )
    return path


def picture(**changes: str) -> dict[str, str]:
    return {
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg",
        "image_commons_file": "File:Synthetic game.jpg",
        "image_source_url": "https://commons.wikimedia.org/wiki/File:Synthetic_game.jpg",
        "image_license": "CC BY-SA 4.0",
        "image_license_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "image_artist": "Auteur fictif",
        "image_attribution": "Photographie synthétique",
        "image_review_status": "approved_by_owner",
        **changes,
    }


def run(path: Path, dry_run: bool = False) -> tuple[dict[str, int], str]:
    output, warnings = StringIO(), StringIO()
    call_command(
        "import_wikidata_games", str(path), dry_run=dry_run, stdout=output, stderr=warnings
    )
    return json.loads(output.getvalue()), warnings.getvalue()


def test_import_provenance_alias_credits_idempotence_and_no_network(tmp_path: Path) -> None:
    path = source(
        tmp_path,
        [
            picture(bgg_ids="123;456;123"),
            {"wikidata_id": "Q900000002", "title_fr": "Sans image", "title_en": ""},
        ],
    )
    with patch("socket.create_connection", side_effect=AssertionError("Aucun réseau")):
        result, _ = run(path)
        second, _ = run(path)
    assert result == {
        "created": 2,
        "existing": 0,
        "conflicts": 0,
        "invalid": 0,
        "aliases": 1,
        "images": 1,
        "images_invalid": 0,
        "images_ignored": 0,
        "dry_run": False,
    }
    assert second["existing"] == 2 and second["created"] == 0 and second["images"] == 0
    game = Game.objects.get(external_id="Q900000001")
    assert game.title == "Le Chemin fictif" and game.external_source == "wikidata"
    assert (
        game.data_source == "Wikidata" and game.data_license == "CC0" and game.bgg_ids == "123;456"
    )
    assert game.aliases.get().title == "Fictional Trail"
    image = game.illustration
    assert image.displayable and image.artist == "Auteur fictif"
    assert image.license == "CC BY-SA 4.0" and image.attribution == "Photographie synthétique"
    assert not OwnedGame.objects.exists()
    account = User.objects.get(email=IMPORT_EMAIL)
    assert not account.is_active and not account.has_usable_password() and not account.is_superuser
    path.unlink()
    assert Game.objects.count() == 2 and GameIllustration.objects.count() == 1


def test_dry_run_performs_no_dml_or_account_creation(tmp_path: Path) -> None:
    path = source(tmp_path, [picture(), picture()])
    with CaptureQueriesContext(connection) as queries:
        result, _ = run(path, True)
    assert result["created"] == 1 and result["images"] == 1 and result["existing"] == 1
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    assert not any(model.objects.exists() for model in (Game, GameAlias, GameIllustration, User))


def test_existing_human_changes_and_hidden_record_are_never_overwritten(tmp_path: Path) -> None:
    path = source(tmp_path, [picture()])
    run(path)
    game = Game.objects.get()
    game.title, game.hidden = "Modification humaine", True
    game.save()
    game.aliases.update(title="Alias humain", title_key="alias humain")
    game.illustration.artist = "Artiste humain"
    game.illustration.save()
    before = Game.objects.values().get()
    image_before = GameIllustration.objects.values().get()
    result, _ = run(path)
    assert result["existing"] == 1
    assert Game.objects.values().get() == before
    assert GameIllustration.objects.values().get() == image_before
    assert game.aliases.get().title == "Alias humain"


@pytest.mark.parametrize("kind", ["bgg_id", "bgg_title", "manual_fr", "manual_en", "hidden"])
def test_conflicts_are_reported_without_merge_or_new_record(tmp_path: Path, kind: str) -> None:
    actor = member()
    title = (
        "Fiche différente"
        if kind == "bgg_id"
        else "Fictional Trail"
        if kind == "manual_en"
        else "Le Chemin fictif"
    )
    game = write_game(actor, {"title": title})
    if kind.startswith("bgg") or kind == "hidden":
        game.external_source, game.external_id = "bgg", "123" if kind == "bgg_id" else "456"
    game.hidden = kind == "hidden"
    game.save()
    item = add_to_collection(actor, game.pk, "", "Notes privées", []) if not game.hidden else None
    before = Game.objects.values().get()
    result, warnings = run(source(tmp_path, [picture(bgg_ids="123")]))
    assert result["conflicts"] == 1 and result["created"] == 0 and "conflit BGG/manuel" in warnings
    assert Game.objects.values().get() == before
    assert not GameAlias.objects.exists() and not GameIllustration.objects.exists()
    assert not User.objects.filter(email=IMPORT_EMAIL).exists()
    if item is not None:
        item.refresh_from_db()
        assert item.notes == "Notes privées" and item.owner == actor


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("wikidata_id", "not-a-Q-id"),
        ("wikidata_id", "Q0"),
        ("wikidata_id", "Q1\x00"),
        ("title_fr", ""),
        ("title_fr", "x" * 121),
        ("title_en", "x" * 121),
        ("data_source", "BGG"),
        ("data_license", "CC BY 4.0"),
        ("bgg_ids", "123;not-a-number"),
    ],
)
def test_invalid_rows_are_skipped(tmp_path: Path, field: str, value: str) -> None:
    result, _ = run(source(tmp_path, [{field: value}]))
    assert result["invalid"] == 1 and result["created"] == 0
    assert not Game.objects.exists() and not User.objects.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"image_url": "http://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg"},
        {
            "image_url": "https://commons.wikimedia.org.evil.test/wiki/Special:FilePath/Synthetic_game.jpg"
        },
        {"image_url": "https://127.0.0.1/private"},
        {"image_url": "javascript:alert(1)"},
        {
            "image_url": "https://user@commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg"
        },
        {"image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg?x=1"},
        {"image_source_url": "https://commons.wikimedia.org/wiki/File:Other_file.jpg"},
        {"image_license_url": "https://creativecommons.org/licenses/by/4.0"},
        {"image_artist": "", "image_attribution": ""},
    ],
)
def test_invalid_images_do_not_prevent_data_import(tmp_path: Path, changes: dict[str, str]) -> None:
    result, warnings = run(source(tmp_path, [picture(**changes)]))
    assert (
        result["created"] == 1
        and result["images_invalid"] == 1
        and "illustration invalide" in warnings
    )
    assert not GameIllustration.objects.exists()


def test_unapproved_images_are_ignored(tmp_path: Path) -> None:
    result, _ = run(source(tmp_path, [picture(image_review_status="rejected")]))
    assert result["created"] == 1 and result["images_ignored"] == 1
    assert not GameIllustration.objects.exists()


def test_http_license_is_canonicalized_and_cc0_can_have_no_artist(tmp_path: Path) -> None:
    result, _ = run(
        source(
            tmp_path,
            [
                picture(
                    image_artist="",
                    image_attribution="",
                    image_license="CC0",
                    image_license_url="http://creativecommons.org/publicdomain/zero/1.0/deed.en",
                )
            ],
        )
    )
    assert result["images"] == 1
    assert (
        GameIllustration.objects.get().license_url
        == "https://creativecommons.org/publicdomain/zero/1.0/deed.en"
    )


def test_artist_can_come_from_attribution_without_inventing_metadata(tmp_path: Path) -> None:
    result, _ = run(
        source(tmp_path, [picture(image_artist="", image_attribution="Auteur attribué")])
    )
    assert result["images"] == 1
    assert GameIllustration.objects.get().artist == ""


def test_failure_of_image_write_rolls_back_game_alias_and_account(tmp_path: Path) -> None:
    with patch.object(GameIllustration, "save", side_effect=RuntimeError("panne")):
        with pytest.raises(RuntimeError):
            run(source(tmp_path, [picture()]))
    assert not any(model.objects.exists() for model in (Game, GameAlias, GameIllustration, User))


def test_header_errors_fail_before_writes(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text("wikidata_id,title_fr\nQ1,Jeu\n")
    with pytest.raises(CommandError, match="En-tête"):
        run(path)
    assert not Game.objects.exists()


def test_fr_english_alias_search_is_unique_private_and_works_for_copies(
    tmp_path: Path, client: Client
) -> None:
    run(
        source(
            tmp_path,
            [picture(title_fr="Les Aventuriers du Rail fictifs", title_en="Ticket to Ride fictif")],
        )
    )
    alice, bob = member(), member("Bob")
    game = Game.objects.get()
    GameAlias.objects.create(game=game, title="Ticket to Ride autre alias fictif")
    assert search(bob, "TICKET TO RIDE").get() == game
    assert search(bob, "aventuriers").get() == game
    assert search(bob, "FICTIF").count() == 1
    community = communities.create(alice, "A")
    Membership.objects.create(community=community, user=bob)
    private = add_to_collection(alice, game.pk, "", "Strictement privé", [])
    shared = add_to_collection(alice, game.pk, "", "Visible", [community.pk])
    client.force_login(bob)
    response = client.get(reverse("catalogue:index"), {"title": "ticket to ride"})
    assert response.context["games"].paginator.count == 1
    assert "Strictement privé" not in response.content.decode()
    response = client.get(reverse("inventory:index"), {"title": "TICKET TO RIDE"})
    assert list(response.context["copies"]) == [shared]
    assert client.get(reverse("inventory:detail", args=[private.pk])).status_code == 404
    with pytest.raises(ValidationError) as error:
        add_to_collection(bob, None, "Ticket to Ride fictif", "", [])
    assert "existe déjà" in str(error.value)
    game.hidden = True
    game.save()
    assert not search(bob, "Ticket to Ride").exists()
    assert client.post(reverse("catalogue:index"), {"game_id": str(game.pk)}).status_code == 404


def test_image_rendering_escapes_credits_and_keeps_license_separate(
    tmp_path: Path, client: Client
) -> None:
    run(source(tmp_path, [picture(image_artist="<script>alert(1)</script>")]))
    actor = member()
    client.force_login(actor)
    game = Game.objects.get()
    response = client.get(reverse("catalogue:detail", args=[game.pk]))
    body = response.content.decode()
    assert "data-commons-image" in body and "CC BY-SA 4.0" in body and "CC0" in body
    assert "&lt;script&gt;" in body and "<script>alert(1)" not in body
    assert (
        'referrerpolicy="no-referrer"' in body and "creativecommons.org/licenses/by-sa/4.0" in body
    )
    assert (
        "img-src 'self' https://commons.wikimedia.org https://upload.wikimedia.org"
        in response["Content-Security-Policy"]
    )
    assert "script-src 'self'" in response["Content-Security-Policy"]
    game.illustration.image_url = "https://evil.test/image.jpg"
    game.illustration.save()
    assert (
        "data-commons-image"
        not in client.get(reverse("catalogue:detail", args=[game.pk])).content.decode()
    )


def test_alias_normalization_and_database_constraints(tmp_path: Path) -> None:
    from django.db import IntegrityError, transaction

    run(source(tmp_path, [picture()]))
    game = Game.objects.get()
    GameAlias.objects.create(game=game, title="Édition de démonstration")
    GameAlias.objects.create(game=game, title="Autre édition de démonstration")
    assert search(member(), "EDITION DE DEMONSTRATION").count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        GameAlias.objects.create(game=game, title="EDITION de démonstration")
    with pytest.raises(IntegrityError), transaction.atomic():
        GameIllustration.objects.filter(game=game).update(review_status="rejected")


@pytest.mark.django_db(transaction=True)
def test_concurrent_imports_keep_game_alias_image_atomic(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    path = source(tmp_path, [picture(wikidata_id=f"Q90000000{i}") for i in range(1, 4)])
    barrier = Barrier(2)

    def import_once(_: int) -> dict[str, int]:
        try:
            barrier.wait(timeout=10)
            return run(path)[0]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(import_once, range(2)))
    assert sum(r["created"] for r in results) == 3
    assert sum(r["existing"] for r in results) == 3
    assert (
        Game.objects.count() == GameAlias.objects.count() == GameIllustration.objects.count() == 3
    )
    assert User.objects.count() == 1
