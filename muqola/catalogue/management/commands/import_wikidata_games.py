import csv
import json
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError

from muqola.catalogue.wikidata_importer import import_wikidata_games


class Command(BaseCommand):
    help = "Importer volontairement le CSV Wikidata local et ses illustrations Commons approuvées."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = import_wikidata_games(options["path"], options["dry_run"], self.stderr.write)
        except (OSError, UnicodeError, csv.Error, ValidationError, DatabaseError) as error:
            raise CommandError(
                f"Import Wikidata interrompu : {error}. "
                "Les lots précédemment validés restent acquis."
            ) from error
        self.stdout.write(json.dumps({**result, "dry_run": options["dry_run"]}))
