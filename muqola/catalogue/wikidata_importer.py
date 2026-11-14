"""Import Wikidata volontaire, distinct du format historique import_games."""

import csv
import re
from collections.abc import Callable
from itertools import islice
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from muqola.catalogue.commons import license_url
from muqola.catalogue.importer import BATCH_SIZE, IMPORT_EMAIL, check_account
from muqola.catalogue.models import Game, GameAlias, GameIllustration, normalized_title
from muqola.identity.models import User

COLUMNS = (
    "wikidata_id",
    "title_fr",
    "title_en",
    "bgg_ids",
    "data_source",
    "data_license",
    "image_url",
    "image_commons_file",
    "image_source_url",
    "image_license",
    "image_license_url",
    "image_artist",
    "image_attribution",
    "image_review_status",
)


def prepare(values: dict[str, str]) -> tuple[Game, GameAlias | None]:
    if any("\x00" in value for value in values.values()):
        raise ValidationError("Caractère nul interdit.")
    if re.fullmatch(r"Q[1-9][0-9]*", values["wikidata_id"]) is None:
        raise ValidationError("Identifiant Wikidata invalide.")
    if values["data_source"].casefold() != "wikidata" or values["data_license"] != "CC0":
        raise ValidationError("Provenance Wikidata et licence de données CC0 attendues.")
    ids = [item.strip() for item in values["bgg_ids"].split(";") if item.strip()]
    if any(re.fullmatch(r"[1-9][0-9]*", item) is None for item in ids):
        raise ValidationError(
            "Références BGG numériques séparées par des points-virgules attendues."
        )
    game = Game(
        title=values["title_fr"],
        title_key=normalized_title(values["title_fr"]),
        external_source="wikidata",
        external_id=values["wikidata_id"],
        data_source="Wikidata",
        data_license="CC0",
        bgg_ids=";".join(sorted(set(ids))),
    )
    game.full_clean(exclude=["created_by"])
    alias = None
    if values["title_en"]:
        alias = GameAlias(
            game=game, title=values["title_en"], title_key=normalized_title(values["title_en"])
        )
        alias.full_clean(exclude=["game"])
    return game, alias


def illustration(values: dict[str, str], game: Game) -> GameIllustration:
    item = GameIllustration(
        game=game,
        image_url=values["image_url"],
        commons_file=values["image_commons_file"],
        source_url=values["image_source_url"],
        license=values["image_license"],
        license_url=license_url(values["image_license_url"]),
        artist=values["image_artist"],
        attribution=values["image_attribution"],
        review_status=values["image_review_status"],
    )
    item.full_clean(exclude=["game"])
    return item


def import_wikidata_games(path: Path, dry_run: bool, warn: Callable[[str], None]) -> dict[str, int]:
    totals = dict.fromkeys(
        (
            "created",
            "existing",
            "conflicts",
            "invalid",
            "aliases",
            "images",
            "images_invalid",
            "images_ignored",
        ),
        0,
    )
    account = User.objects.filter(email=IMPORT_EMAIL).first()
    if account is not None:
        check_account(account)
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(COLUMNS)
            or set(reader.fieldnames) != set(COLUMNS)
        ):
            raise ValidationError("En-tête CSV Wikidata invalide.")
        records = ((reader.line_num, row) for row in reader)
        while batch := list(islice(records, BATCH_SIZE)):
            counts = dict.fromkeys(totals, 0)
            with transaction.atomic():
                for line, row in batch:
                    if None in row or any(v is None for v in row.values()):
                        counts["invalid"] += 1
                        warn(f"Ligne {line} : nombre de colonnes invalide.")
                        continue
                    values = {key: value.strip() for key, value in row.items()}
                    qid = values["wikidata_id"]
                    if len(qid) > 120 or re.fullmatch(r"Q[1-9][0-9]*", qid) is None:
                        counts["invalid"] += 1
                        warn(f"Ligne {line} : identifiant Wikidata invalide.")
                        continue
                    existing = Game.objects.filter(external_source="wikidata", external_id=qid)
                    if qid in seen or existing.exists():
                        counts["existing"] += 1
                        seen.add(qid)
                        continue
                    try:
                        game, alias = prepare(values)
                    except ValidationError:
                        if existing.exists():
                            counts["existing"] += 1
                            seen.add(qid)
                        else:
                            counts["invalid"] += 1
                            warn(f"Ligne {line} : données de jeu ou alias invalides.")
                        continue
                    keys = {game.title_key, normalized_title(values["title_en"])} - {""}
                    conflicts = Game.objects.filter(
                        Q(external_source="bgg", external_id__in=game.bgg_ids.split(";"))
                        | (Q(external_source__isnull=True) | Q(external_source="bgg"))
                        & Q(title_key__in=keys)
                    )
                    if conflicts.exists():
                        counts["conflicts"] += 1
                        warn(
                            f"Ligne {line} ({qid}) : conflit BGG/manuel, aucune fusion ni création."
                        )
                        continue
                    picture = None
                    if values["image_review_status"] == "approved_by_owner":
                        try:
                            picture = illustration(values, game)
                        except ValidationError:
                            counts["images_invalid"] += 1
                            warn(
                                f"Ligne {line} ({qid}) : illustration invalide ignorée, "
                                "jeu conservé."
                            )
                    elif any(
                        values[field]
                        for field in COLUMNS
                        if field.startswith("image_") and field != "image_review_status"
                    ):
                        counts["images_ignored"] += 1
                        warn(f"Ligne {line} ({qid}) : illustration non approuvée ignorée.")
                    if not dry_run:
                        try:
                            with transaction.atomic():
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
                                game.save(force_insert=True)
                                if alias is not None:
                                    alias.save()
                                if picture is not None:
                                    picture.save()
                        except IntegrityError:
                            if not existing.exists():
                                raise
                            counts["existing"] += 1
                            seen.add(qid)
                            continue
                    counts["created"] += 1
                    counts["aliases"] += int(alias is not None)
                    counts["images"] += int(picture is not None)
                    seen.add(qid)
            for key, count in counts.items():
                totals[key] += count
    return totals
