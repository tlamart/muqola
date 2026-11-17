from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone

from muqola.catalogue.models import Game, GameReport
from muqola.communities.models import Membership
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from muqola.loans.services import close_ineligible_requests
from muqola.operations.models import DeletionRequest, OperatorAction


def operator(user: User) -> None:
    verified(user)
    if not User.objects.filter(pk=user.pk, is_superuser=True).exists():
        raise PermissionDenied


def audit(user: User, action: str, target: str, reason: str) -> None:
    if not reason.strip() or len(reason) > 500:
        raise ValidationError("Motif non sensible de 1 à 500 caractères obligatoire.")
    OperatorAction.objects.create(
        operator=user, action=action, target=target, reason=reason.strip()
    )


def disable_user(user: User, target_id: int, reason: str) -> None:
    with domain_write(user):
        operator(user)
        target = get_object_or_404(User, pk=target_id)
        if target.pk == user.pk:
            raise ValidationError("Ne désactivez pas votre propre compte opérateur.")
        audit(user, "disable_user", str(target.pk), reason)
        target.is_active = False
        target.save()
        OwnedGame.objects.filter(owner=target).update(withdrawn=True)
        close_ineligible_requests(user, participant_id=target.pk)


def recover_community_admin(user: User, community_id: UUID, target_id: int, reason: str) -> None:
    with domain_write(user):
        operator(user)
        if Membership.objects.filter(
            community_id=community_id,
            active=True,
            role=Membership.Role.ADMIN,
            user__is_active=True,
            user__email_verified_at__isnull=False,
        ).exists():
            raise ValidationError(
                "La communauté possède déjà un administrateur actif et vérifié. "
                "Utilisez le transfert d'administration."
            )
        target = Membership.objects.filter(
            community_id=community_id,
            user_id=target_id,
            active=True,
            user__is_active=True,
            user__email_verified_at__isnull=False,
        ).first()
        if target is None:
            raise ValidationError(
                "Membre cible actif et vérifié introuvable dans cette communauté."
            )
        target.role = Membership.Role.ADMIN
        target.save(update_fields=["role"])
        audit(user, "recover_community_admin", f"{community_id}:{target_id}", reason)


def moderate_game(
    user: User, game_id: UUID, reason: str, metadata: dict[str, Any] | None = None
) -> None:
    if metadata is not None:
        from muqola.catalogue.moderation import correct

        correct(user, game_id, reason, metadata)
        return
    with domain_write(user):
        operator(user)
        game = get_object_or_404(Game, pk=game_id, merged_into__isnull=True)
        audit(user, "hide_game", str(game.pk), reason)
        game.hidden = True
        OwnedGame.objects.filter(game=game).update(withdrawn=True)
        game.full_clean()
        game.save()
        for copy_id in OwnedGame.objects.filter(game=game).values_list("pk", flat=True):
            close_ineligible_requests(user, copy_id=copy_id)
        GameReport.objects.filter(game=game, resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )


def request_deletion(user: User, reason: str = "") -> None:
    # Exercising privacy rights must not require an adult attestation.
    with domain_write(user, require_adult=False):
        entry, _ = DeletionRequest.objects.get_or_create(user=user)
        entry.reason = reason.strip()
        entry.full_clean()
        entry.save()


def retry_notifications(user: User) -> int:
    from muqola.notifications.services import retry_failed

    with domain_write(user):
        operator(user)
        count = retry_failed()
        audit(user, "retry_notifications", "failed", "Reprise manuelle des notifications en échec")
        return count
