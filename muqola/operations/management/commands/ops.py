import json
from pathlib import Path
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Count

from muqola.catalogue.models import GameReport
from muqola.identity.models import User
from muqola.notifications.models import EmailOutbox
from muqola.operations import services
from muqola.operations.models import DeletionRequest


class Command(BaseCommand):
    help = "Console privée : reprise, signalements et sécurité, sans annuaire des prêts."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "action",
            choices=[
                "outbox-status",
                "retry-failed",
                "reports",
                "deletion-requests",
                "disable-user",
                "recover-community-admin",
                "hide-game",
                "correct-game",
            ],
        )
        parser.add_argument("--operator", required=True)
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--community-id", type=UUID)
        parser.add_argument("--game-id", type=UUID)
        parser.add_argument("--metadata-file", type=Path)
        parser.add_argument("--reason", default="")

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(
            email=options["operator"].strip().lower(),
            is_active=True,
            is_superuser=True,
            email_verified_at__isnull=False,
        ).first()
        if user is None:
            raise CommandError(
                "Opérateur non autorisé. Cette console exige aussi un accès OS de confiance."
            )
        action = options["action"]
        if action == "outbox-status":
            result: Any = list(EmailOutbox.objects.values("status").annotate(count=Count("id")))
        elif action == "retry-failed":
            result = {"requeued": services.retry_notifications(user)}
        elif action == "reports":
            result = list(
                GameReport.objects.filter(resolved_at__isnull=True).values(
                    "id", "game_id", "reason"
                )[:100]
            )
        elif action == "deletion-requests":
            result = list(
                DeletionRequest.objects.filter(processed_at__isnull=True).values(
                    "id", "user_id", "created_at"
                )[:100]
            )
        else:
            try:
                if action == "disable-user" and options["user_id"]:
                    services.disable_user(user, options["user_id"], options["reason"])
                elif action == "recover-community-admin":
                    if options["community_id"] is None or options["user_id"] is None:
                        raise CommandError("--community-id et --user-id sont obligatoires.")
                    services.recover_community_admin(
                        user, options["community_id"], options["user_id"], options["reason"]
                    )
                elif action in {"hide-game", "correct-game"} and options["game_id"]:
                    metadata = None
                    if action == "correct-game":
                        if options["metadata_file"] is None:
                            raise CommandError(
                                "--metadata-file JSON est obligatoire pour une correction."
                            )
                        metadata = json.loads(options["metadata_file"].read_text())
                        if not isinstance(metadata, dict):
                            raise CommandError("Objet JSON de métadonnées attendu.")
                    services.moderate_game(user, options["game_id"], options["reason"], metadata)
                else:
                    raise CommandError("Identifiant de cible obligatoire.")
            except ValidationError as error:
                raise CommandError(" ".join(error.messages)) from error
            result = {"status": "recorded"}
        self.stdout.write(json.dumps(result, default=str, ensure_ascii=True))
