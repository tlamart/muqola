"""Private staging gate; preserves security/legal checks and requires SMTP capture."""

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from muqola.operations.readiness import readiness_issues


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        issues = readiness_issues(staging=True)
        self.stdout.write(json.dumps({"ready_for_staging": not issues, "issues": issues}))
        if issues:
            raise CommandError("Staging incomplet ; consulter les codes sans secrets.")
