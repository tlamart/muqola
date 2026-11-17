"""Strict public-production gate; staging never satisfies this command."""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from muqola.operations.readiness import readiness_issues


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        issues = readiness_issues()
        self.stdout.write(json.dumps({"ready_for_launch": not issues, "issues": issues}))
        if issues:
            raise CommandError("Préparation incomplète ; voir les codes sans secrets ci-dessus.")
