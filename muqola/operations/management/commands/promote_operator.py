"""Explicit OS-trusted promotion; never creates accounts or fabricates verification."""

import json
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from muqola.core.transactions import domain_write
from muqola.identity.models import User
from muqola.operations.services import audit, audit_reason, operator


class Command(BaseCommand):
    help = "Promeut un compte existant vérifié/adulte ; accès OS de confiance obligatoire."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--confirm-email", required=True)
        parser.add_argument("--reason", required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--bootstrap", action="store_true")
        mode.add_argument("--operator")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--if-needed", action="store_true")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--deployment-env", choices=("staging", "production"))

    def handle(self, *args: Any, **options: Any) -> None:
        environment = options["deployment_env"]
        if environment and (
            settings.APP_ENV != "production" or settings.DEPLOYMENT_ENV != environment
        ):
            raise CommandError(
                "Le contexte applicatif ne correspond pas à l’environnement demandé."
            )
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
                reason = audit_reason(options["reason"])
                target = User.objects.select_for_update().get(pk=target.pk)
                if not target.has_usable_password():
                    raise ValidationError(
                        "Le compte cible doit posséder un mot de passe utilisable."
                    )
                already_operator = target.is_superuser and target.is_staff
                if already_operator and not options["if_needed"]:
                    raise ValidationError("Ce compte est déjà opérateur web ; aucune modification.")
                if options["bootstrap"]:
                    superusers = User.objects.filter(is_superuser=True)
                    if already_operator and options["if_needed"]:
                        superusers = superusers.exclude(pk=target.pk)
                    if superusers.exists():
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
                if already_operator:
                    status = "unchanged"
                elif options["dry_run"]:
                    status = "would_promote"
                else:
                    target.is_staff = target.is_superuser = True
                    target.save(update_fields=["is_staff", "is_superuser", "updated_at"])
                    audit(author, action, str(target.pk), reason)
                    status = "promoted"
        except (PermissionDenied, ValidationError) as error:
            message = "Compte actif, vérifié et adulte requis pour la cible et l’opérateur."
            if isinstance(error, ValidationError):
                message = " ".join(error.messages)
            raise CommandError(message) from error
        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "status": status,
                        "dry_run": bool(options["dry_run"]),
                        "environment": settings.DEPLOYMENT_ENV,
                    }
                )
            )
        else:
            messages = {
                "promoted": "Promotion opérateur enregistrée et auditée. Aucun secret affiché.",
                "would_promote": "Simulation validée : promotion possible. Aucune modification.",
                "unchanged": "Ce compte est déjà opérateur web ; aucune modification.",
            }
            self.stdout.write(messages[status])
