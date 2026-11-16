"""Validations Wikidata/Commons conservées ; ingestion CSV désactivée en B."""

import re
from collections.abc import Callable
from pathlib import Path

from django.core.exceptions import ValidationError

from muqola.catalogue.commons import license_url
from muqola.catalogue.models import Game, GameAlias, GameIllustration, normalized_title

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
    raise ValidationError(
        "Les imports BGG/Wikidata sont désactivés : proposez des fiches "
        "puis faites-les valider. Aucune donnée existante n’a été modifiée."
    )
