"""Ancien format CSV conservé ; ingestion désactivée par la refonte B."""

from collections.abc import Callable
from pathlib import Path

from django.core.exceptions import ValidationError

from muqola.identity.models import User

COLUMNS = (
    "title",
    "year",
    "publisher",
    "players_min",
    "players_max",
    "duration",
    "description",
    "external_source",
    "external_id",
)
NUMBERS = {"year", "players_min", "players_max", "duration"}
IMPORT_EMAIL = "catalogue-import@muqola.invalid"
BATCH_SIZE = 250


def check_account(user: User) -> None:
    if (
        user.is_active
        or user.is_staff
        or user.is_superuser
        or user.email_verified_at is not None
        or user.has_usable_password()
    ):
        raise ValidationError("Le compte réservé à l'import n'est pas un compte technique sûr.")


def import_games(path: Path, dry_run: bool, warn: Callable[[str], None]) -> dict[str, int]:
    raise ValidationError(
        "Les imports BGG/Wikidata sont désactivés : proposez des fiches "
        "puis faites-les valider. Aucune donnée existante n’a été modifiée."
    )
