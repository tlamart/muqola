import secrets
from datetime import timedelta
from uuid import UUID

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from muqola.communities.models import (
    Community,
    CommunityInvite,
    InvitationEvent,
    Membership,
    PendingJoin,
)
from muqola.core.secrets import secret_cipher
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User
from muqola.identity.services import token_digest


def membership(user: User, community_id: UUID, admin: bool = False) -> Membership:
    verified(user)
    query = Membership.objects.select_related("community").filter(
        user=user, active=True, community_id=community_id, community__archived_at__isnull=True
    )
    if admin:
        query = query.filter(role=Membership.Role.ADMIN)
    return get_object_or_404(query)


def create(user: User, name: str, description: str = "", illustration: str = "table") -> Community:
    with domain_write(user):
        community = Community(
            name=name.strip(),
            description=description.strip(),
            created_by=user,
            illustration=illustration,
        )
        community.full_clean()
        community.save()
        Membership.objects.create(community=community, user=user, role=Membership.Role.ADMIN)
        return community


def update(
    user: User, community_id: UUID, name: str, description: str, illustration: str = "table"
) -> None:
    with domain_write(user):
        community = membership(user, community_id, admin=True).community
        community.name, community.description = name.strip(), description.strip()
        community.illustration = illustration
        community.full_clean()
        community.save()


def invite(user: User, community_id: UUID, days: int | None = None) -> CommunityInvite:
    with domain_write(user):
        community = membership(user, community_id, admin=True).community
        if days is not None and not 1 <= days <= 30:
            raise ValidationError("La durée doit être comprise entre 1 et 30 jours.")
        CommunityInvite.objects.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
            community=community,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now(), encrypted_token="")
        InvitationEvent.objects.create(community=community, actor=user, action="rotate")
        raw = secrets.token_urlsafe(32)
        return CommunityInvite.objects.create(
            community=community,
            created_by=user,
            digest=token_digest(raw),
            encrypted_token=secret_cipher("community-invite").encrypt(raw.encode()).decode(),
            expires_at=timezone.now() + timedelta(days=days) if days is not None else None,
        )


def revoke(user: User, community_id: UUID, invite_id: UUID) -> None:
    with domain_write(user):
        membership(user, community_id, admin=True)
        item = get_object_or_404(CommunityInvite, pk=invite_id, community_id=community_id)
        InvitationEvent.objects.create(community=item.community, actor=user, action="revoke")
        item.revoked_at = timezone.now()
        item.encrypted_token = ""
        item.save(update_fields=["revoked_at", "encrypted_token"])


def valid_invite(digest: str) -> CommunityInvite | None:
    return (
        CommunityInvite.objects.select_related("community")
        .filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
            digest=digest,
            revoked_at__isnull=True,
            community__archived_at__isnull=True,
        )
        .first()
    )


def remember(user: User, digest: str) -> None:
    if len(digest) == 64:
        PendingJoin.objects.update_or_create(
            user=user, defaults={"digest": digest, "created_at": timezone.now()}
        )


def join(user: User, digest: str) -> Community:
    with domain_write(user):
        item = valid_invite(digest)
        if item is None:
            raise ValidationError(
                "Ce lien est expiré ou révoqué. Demandez un nouveau lien aux membres."
            )
        member, _ = Membership.objects.get_or_create(user=user, community=item.community)
        if not member.active:
            member.active, member.role, member.joined_at = (
                True,
                Membership.Role.MEMBER,
                timezone.now(),
            )
            member.save()
        PendingJoin.objects.filter(user=user).delete()
        return item.community


def cancel_join(user: User) -> None:
    with domain_write(user):
        PendingJoin.objects.filter(user=user).delete()


def remove(user: User, community_id: UUID, target_id: int) -> None:
    with domain_write(user):
        actor = membership(user, community_id, admin=target_id != user.pk)
        target = get_object_or_404(
            Membership, community_id=community_id, user_id=target_id, active=True
        )
        if (
            target.role == Membership.Role.ADMIN
            and Membership.objects.filter(
                community_id=community_id, active=True, role=Membership.Role.ADMIN
            ).count()
            == 1
        ):
            raise ValidationError(
                "Transférez d'abord l'administration : la communauté doit garder un administrateur."
            )
        target.active, target.role = False, Membership.Role.MEMBER
        target.save(update_fields=["active", "role"])
        from muqola.inventory.services import remove_community_visibility

        remove_community_visibility(target_id, community_id)
        from muqola.loans.services import close_ineligible_requests

        close_ineligible_requests(user, participant_id=target_id)
        del actor


def transfer(user: User, community_id: UUID, target_id: int) -> None:
    with domain_write(user):
        actor = membership(user, community_id, admin=True)
        target = get_object_or_404(
            Membership,
            community_id=community_id,
            user_id=target_id,
            active=True,
            user__is_active=True,
            user__email_verified_at__isnull=False,
        )
        if target.user_id == user.pk:
            raise ValidationError("Choisissez un autre membre.")
        target.role = Membership.Role.ADMIN
        target.save(update_fields=["role"])
        actor.role = Membership.Role.MEMBER
        actor.save(update_fields=["role"])


def current_invitation(user: User, community_id: UUID) -> tuple[CommunityInvite | None, str]:
    # Même verrou que retrait/rotation : autorisation revérifiée avant déchiffrement.
    with domain_write(user):
        membership(user, community_id)
        item = (
            CommunityInvite.objects.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
                community_id=community_id,
                revoked_at__isnull=True,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        link = ""
        if item and item.encrypted_token:
            try:
                raw = (
                    secret_cipher("community-invite")
                    .decrypt(item.encrypted_token.encode())
                    .decode()
                )
            except (InvalidToken, UnicodeError):
                pass
            else:
                link = f"{settings.APP_BASE_URL}/communities/invite/{raw}/"
        return item, link
