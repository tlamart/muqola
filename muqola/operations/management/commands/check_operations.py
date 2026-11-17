"""Private read-only aggregate diagnostics; no account, title, token or payload."""

import json
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from muqola.notifications.models import EmailOutbox


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        pending = EmailOutbox.objects.filter(status=EmailOutbox.Status.PENDING)
        result = {
            "database": True,
            "outbox_failed": EmailOutbox.objects.filter(status=EmailOutbox.Status.FAILED).count(),
            "outbox_late": pending.filter(created_at__lt=now - timedelta(minutes=15)).count(),
        }
        self.stdout.write(json.dumps(result))
