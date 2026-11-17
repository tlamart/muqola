"""Explicit, repeatable post-migration grants; runtime cannot invoke this successfully."""

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            if cursor.fetchone()[0] not in {"muqola_migrate", "muqola_admin"}:
                raise CommandError("Rôle de maintenance requis.")
            script = Path(settings.BASE_DIR) / "deploy/postgres/runtime-grants.sql"
            cursor.execute(script.read_text())
        self.stdout.write("Privilèges runtime appliqués.")
