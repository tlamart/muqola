import signal
import threading
import time
from pathlib import Path
from typing import Any

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections
from django.utils import timezone

from muqola.identity.services import purge_ephemeral_data
from muqola.notifications.services import enqueue_pending_events, purge_notifications, send_due


class Command(BaseCommand):
    help = "Traite l'outbox persistée des comptes/prêts, reprise et rétention incluses."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--heartbeat-file", type=Path)

    def handle(self, *args: Any, **options: Any) -> None:
        stop = threading.Event()
        if not options["once"]:
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        last_purge = 0.0
        last_session_purge = None
        while not stop.is_set():
            close_old_connections()
            enqueue_pending_events()
            count = send_due(limit=20 if options["once"] else 1)
            if time.monotonic() - last_purge >= 3600:
                purge_ephemeral_data()
                purge_notifications()
                last_purge = time.monotonic()
            if last_session_purge != timezone.now().date():
                Session.objects.filter(expire_date__lt=timezone.now()).delete()
                last_session_purge = timezone.now().date()
            if options["heartbeat_file"] is not None:
                options["heartbeat_file"].touch(mode=0o600, exist_ok=True)
            if options["once"]:
                self.stdout.write(f"{count} message(s) traité(s).")
                break
            stop.wait(0.1 if count else 5)
