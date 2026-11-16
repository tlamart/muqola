import json
from pathlib import Path
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Count

from muqola.catalogue.models import GameReport
from muqola.catalogue.services import FIELDS
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
                "catalogue-inventory",
                "catalogue-review",
                "approve-game",
                "reject-game",
                "request-game-changes",
                "merge-games",
            ],
        )
        parser.add_argument("--operator", required=True)
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--community-id", type=UUID)
        parser.add_argument("--game-id", type=UUID)
        parser.add_argument("--metadata-file", type=Path)
        parser.add_argument("--reason", default="")
        parser.add_argument("--homonym-reason", default="")
        parser.add_argument("--target-game-id", type=UUID)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")

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
        result: Any
        action = options["action"]
        if (options["apply"] or options["dry_run"]) and action != "merge-games":
            raise CommandError("--apply/--dry-run sont réservés à merge-games.")
        if action in {
            "catalogue-inventory",
            "catalogue-review",
            "approve-game",
            "reject-game",
            "request-game-changes",
            "merge-games",
            "correct-game",
        }:
            try:
                result = self.catalogue_action(user, action, options)
            except (ValidationError, ValueError, TypeError, OSError) as error:
                if isinstance(error, ValidationError):
                    raise CommandError(" ".join(error.messages)) from error
                raise CommandError("Paramètres ou fichier JSON invalides.") from error
        elif action == "outbox-status":
            result = list(EmailOutbox.objects.values("status").annotate(count=Count("id")))
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

    def catalogue_action(self, user: User, action: str, options: dict[str, Any]) -> Any:
        from muqola.catalogue import moderation
        from muqola.catalogue.models import Game

        if action == "catalogue-inventory":
            return moderation.inventory(user)
        if action == "catalogue-review":
            query = Game.objects.filter(merged_into__isnull=True).order_by("created_at", "id")
            if options["game_id"]:
                query = query.filter(pk=options["game_id"])
            else:
                query = query.filter(
                    moderation_status__in=[Game.Status.PENDING, Game.Status.LEGACY]
                )
            return [
                {
                    "id": str(game.pk),
                    "title": game.title,
                    "kind": game.kind,
                    "base_game_id": str(game.base_game_id) if game.base_game_id else None,
                    "status": game.moderation_status,
                    "hidden": game.hidden,
                    "proposal_reason": game.proposal_reason,
                    "external_ids": list(game.external_identifiers.values("source", "identifier")),
                    "legacy_external_reference": {
                        "source": game.external_source,
                        "identifier": game.external_id,
                        "bgg_ids": game.bgg_ids,
                    },
                    "metadata": {field: getattr(game, field) for field in FIELDS},
                    "aliases": list(game.aliases.values_list("title", flat=True)),
                    "similar": list(
                        moderation.duplicates(game).values("id", "title", "moderation_status")[:20]
                    ),
                }
                for game in query[:100]
            ]
        if options["game_id"] is None:
            raise CommandError("--game-id est obligatoire.")
        if action == "merge-games":
            if options["target_game_id"] is None:
                raise CommandError("--target-game-id est obligatoire.")
            return moderation.merge(
                user,
                options["game_id"],
                options["target_game_id"],
                options["reason"],
                dry_run=not options["apply"],
            )
        metadata: dict[str, Any] = {}
        if options["metadata_file"] is not None:
            metadata = json.loads(options["metadata_file"].read_text())
            if not isinstance(metadata, dict):
                raise CommandError("Objet JSON de métadonnées attendu.")
        if action == "correct-game":
            if not metadata:
                raise CommandError("--metadata-file JSON est obligatoire pour une correction.")
            moderation.correct(
                user, options["game_id"], options["reason"], metadata, options["homonym_reason"]
            )
        else:
            status = {
                "approve-game": Game.Status.APPROVED,
                "reject-game": Game.Status.REJECTED,
                "request-game-changes": Game.Status.PENDING,
            }[action]
            moderation.decide(
                user,
                options["game_id"],
                status,
                options["reason"],
                metadata,
                options["homonym_reason"],
            )
        return {"status": "recorded"}
