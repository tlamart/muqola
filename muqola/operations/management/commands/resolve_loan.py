from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError, CommandParser

from muqola.identity.models import User
from muqola.loans.services import resolve


class Command(BaseCommand):
    help = "Résout explicitement un prêt bloqué ; opérateur superuser actif et vérifié requis."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("loan_id", type=UUID)
        parser.add_argument("--operator", required=True)
        parser.add_argument("--resolution", choices=["RETURNED", "CANCELLED"], required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(
            email=options["operator"].strip().lower(),
            is_active=True,
            is_superuser=True,
            email_verified_at__isnull=False,
        ).first()
        if user is None:
            raise CommandError("Opérateur non autorisé.")
        resolve(user, options["loan_id"], options["resolution"], options["reason"])
        self.stdout.write("Résolution enregistrée et tracée.")
