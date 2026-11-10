from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from muqola.identity.models import User


class Command(BaseCommand):
    help = "Crée un opérateur fictif sans connexion web, exclusivement en développement."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default="operateur@example.test")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        if settings.APP_ENV != "development" or not email.endswith("@example.test"):
            raise CommandError("Développement et adresse synthétique @example.test obligatoires.")
        if User.objects.filter(email=email).exists():
            raise CommandError("Ce compte existe déjà : aucun compte existant n'a été promu.")
        User.objects.create_user(
            email,
            display_name="Opérateur fictif",
            is_staff=True,
            is_superuser=True,
            email_verified_at=timezone.now(),
        )
        self.stdout.write(
            "Opérateur fictif créé, mot de passe inutilisable ; console privée seulement."
        )
