from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Envoie un message synthétique vers la capture SMTP locale uniquement."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--to", default="test@example.test")

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.APP_ENV != "development" or settings.EMAIL_HOST not in {
            "mailpit",
            "localhost",
            "127.0.0.1",
        }:
            raise CommandError("Cette commande est réservée à la capture SMTP de développement.")
        if not str(options["to"]).endswith("@example.test"):
            raise CommandError("Utiliser une adresse synthétique @example.test.")
        send_mail(
            "Muqola — test local",
            "Capture de développement du lot 0.",
            settings.DEFAULT_FROM_EMAIL,
            [options["to"]],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS("Message transmis à la capture SMTP locale."))
