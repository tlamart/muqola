import signal
import threading
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from muqola.identity.services import purge_ephemeral_data
from muqola.notifications.services import send_due


class Command(BaseCommand):
    help = "Traite les e-mails de compte persistés ; réessaie après erreur SMTP."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        stop = threading.Event()
        if not options["once"]:
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        ticks = 0
        while not stop.is_set():
            close_old_connections()
            count = send_due()
            if ticks % 720 == 0:
                purge_ephemeral_data()
            if options["once"]:
                self.stdout.write(f"{count} message(s) traité(s).")
                break
            ticks += 1
            stop.wait(5)
