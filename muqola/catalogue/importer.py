"""Import explicite de métadonnées locales, sans client réseau ni mise à jour."""

import csv
from collections.abc import Callable
from itertools import islice
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from muqola.catalogue.models import Game, normalized_title
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
    totals = {"created": 0, "existing": 0, "ignored": 0, "invalid": 0}
    account = User.objects.filter(email=IMPORT_EMAIL).first()
    if account is not None:
        check_account(account)
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames is None or (
            len(reader.fieldnames) != len(COLUMNS) or set(reader.fieldnames) != set(COLUMNS)
        ):
            raise ValidationError("En-tête CSV attendu : " + ",".join(COLUMNS))
        records = ((reader.line_num, row) for row in reader)
        while batch := list(islice(records, BATCH_SIZE)):
            counts = dict.fromkeys(totals, 0)
            # Un lot validé reste acquis ; une erreur fatale annule tout le lot courant.
            with transaction.atomic():
                for offset, row in batch:
                    if None in row or any(value is None for value in row.values()):
                        counts["invalid"] += 1
                        warn(f"Ligne {offset} : nombre de colonnes invalide.")
                        continue
                    values = {key: value.strip() for key, value in row.items()}
                    if not any(values.values()) or not (
                        values["external_source"] or values["external_id"]
                    ):
                        counts["ignored"] += 1
                        warn(f"Ligne {offset} : ignorée, identifiant externe absent.")
                        continue
                    key = (values["external_source"], values["external_id"])
                    try:
                        for name, value in values.items():
                            if "\x00" in value:
                                raise ValidationError({name: "Caractère nul interdit."})
                        game = Game(
                            title=values["title"],
                            publisher=values["publisher"],
                            description=values["description"],
                            external_source=key[0] or None,
                            external_id=key[1] or None,
                        )
                        for name in NUMBERS:
                            try:
                                setattr(game, name, int(values[name]) if values[name] else None)
                            except ValueError as error:
                                raise ValidationError({name: "Entier attendu."}) from error
                        if (
                            key in seen
                            or Game.objects.filter(
                                external_source=key[0], external_id=key[1]
                            ).exists()
                        ):
                            counts["existing"] += 1
                            seen.add(key)
                            continue
                        game.title_key = normalized_title(game.title)
                        game.full_clean(exclude=["created_by"])
                    except ValidationError as error:
                        if Game.objects.filter(external_source=key[0], external_id=key[1]).exists():
                            counts["existing"] += 1
                            seen.add(key)
                            continue
                        counts["invalid"] += 1
                        fields = ", ".join(error.message_dict)
                        warn(f"Ligne {offset} : données invalides ({fields}).")
                        continue
                    if not dry_run:
                        if account is None:
                            account, _ = User.objects.get_or_create(
                                email=IMPORT_EMAIL,
                                defaults={
                                    "display_name": "Catalogue importé (compte technique)",
                                    "is_active": False,
                                    "password": "!",
                                },
                            )
                        check_account(account)
                        game.created_by = account
                        try:
                            with transaction.atomic():
                                game.save(force_insert=True)
                        except IntegrityError:
                            if not Game.objects.filter(
                                external_source=key[0], external_id=key[1]
                            ).exists():
                                raise
                            counts["existing"] += 1
                            seen.add(key)
                            continue
                    counts["created"] += 1
                    seen.add(key)
            for name, count in counts.items():
                totals[name] += count
    return totals
