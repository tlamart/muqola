import csv
import json
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError

from muqola.catalogue.importer import import_games


class Command(BaseCommand):
    help = "Importer explicitement un CSV local, sans écraser les jeux existants."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = import_games(options["path"], options["dry_run"], self.stderr.write)
        except (OSError, UnicodeError, csv.Error, ValidationError, DatabaseError) as error:
            raise CommandError(
                f"Import interrompu : {error}. Les lots déjà validés restent acquis ; "
                "corriger le fichier puis relancer sans risque de doublons."
            ) from error
        self.stdout.write(json.dumps({**result, "dry_run": options["dry_run"]}))
