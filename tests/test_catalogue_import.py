"""The historical import entrypoints must now be inert, including dry runs."""

from collections.abc import Callable
from io import StringIO
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from muqola.catalogue.importer import import_games
from muqola.catalogue.wikidata_importer import import_wikidata_games
from tests.helpers import approved_game, member

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("command", ["import_games", "import_wikidata_games"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_import_commands_are_disabled_without_read_or_write(
    tmp_path: Path, command: str, dry_run: bool
) -> None:
    game = approved_game(member(), {"title": "Donnée existante conservée"})
    before = dict(game.__dict__)
    # This path deliberately does not exist: no catalogue should even be opened.
    with (
        CaptureQueriesContext(connection) as queries,
        pytest.raises(CommandError, match="désactivés"),
    ):
        call_command(command, str(tmp_path / "missing.csv"), dry_run=dry_run, stdout=StringIO())
    assert not any(q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries)
    game.refresh_from_db()
    assert {key: value for key, value in before.items() if not key.startswith("_")} == {
        key: value for key, value in game.__dict__.items() if not key.startswith("_")
    }


@pytest.mark.parametrize("entrypoint", [import_games, import_wikidata_games])
def test_python_entrypoint_cannot_bypass_disabled_command(
    tmp_path: Path, entrypoint: Callable[[Path, bool, Callable[[str], None]], dict[str, int]]
) -> None:
    with pytest.raises(ValidationError, match="désactivés"):
        entrypoint(tmp_path / "missing.csv", False, lambda _: None)
