"""Explicit OS-trusted promotion; never creates accounts or fabricates verification."""

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from muqola.core.transactions import domain_write
from muqola.identity.models import User
from muqola.operations.services import audit, operator


class Command(BaseCommand):
    help = "Promeut un compte existant vérifié/adulte ; accès OS de confiance obligatoire."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--confirm-email", required=True)
        parser.add_argument("--reason", required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--bootstrap", action="store_true")
        mode.add_argument("--operator")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        if email != options["confirm_email"].strip().lower():
            raise CommandError("La confirmation ne correspond pas à la cible.")
        target = User.objects.filter(email=email).first()
        if target is None:
            raise CommandError(
                "Compte cible introuvable : inscription et vérification préalables requises."
            )
        try:
            with domain_write(target):
                target = User.objects.select_for_update().get(pk=target.pk)
                if not target.has_usable_password():
                    raise ValidationError(
                        "Le compte cible doit posséder un mot de passe utilisable."
                    )
                if target.is_superuser and target.is_staff:
                    raise ValidationError("Ce compte est déjà opérateur web ; aucune modification.")
                if options["bootstrap"]:
                    if User.objects.filter(is_superuser=True).exists():
                        raise ValidationError(
                            "Un superuser existe déjà : amorçage refusé. Utilisez --operator."
                        )
                    author = target
                    action = "bootstrap_operator"
                else:
                    existing_operator = User.objects.filter(
                        email=options["operator"].strip().lower()
                    ).first()
                    if existing_operator is None:
                        raise PermissionDenied
                    author = existing_operator
                    operator(author)
                    action = "promote_operator"
                target.is_staff = target.is_superuser = True
                target.save(update_fields=["is_staff", "is_superuser", "updated_at"])
                audit(author, action, str(target.pk), options["reason"])
        except (PermissionDenied, ValidationError) as error:
            message = "Compte actif, vérifié et adulte requis pour la cible et l’opérateur."
            if isinstance(error, ValidationError):
                message = " ".join(error.messages)
            raise CommandError(message) from error
        self.stdout.write("Promotion opérateur enregistrée et auditée. Aucun secret affiché.")
