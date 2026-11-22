"""Operator-assisted privacy operations. Never invoked by startup, migrations or worker.

Plans contain identifiers/counts only. Hashes bind current records and expire daily.
All domain mutations share the application advisory lock. External mail stays outside it.
"""

import calendar
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from muqola.catalogue.models import Game, GameDecision, GameMerge, GameReport
from muqola.communities.models import (
    Community,
    CommunityInvite,
    InvitationEvent,
    Membership,
    PendingJoin,
)
from muqola.identity.models import ERASURE_PLACEHOLDER_EMAIL, AccountToken, User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.loans.models import Loan, LoanEvent
from muqola.loans.services import ACTIVE, close_ineligible_requests
from muqola.notifications.models import EmailOutbox
from muqola.operations.models import DeletionRequest, InactivityNotice, PrivacyHold, PrivacyReceipt
from muqola.operations.services import operator

TOMBSTONE_EMAIL = ERASURE_PLACEHOLDER_EMAIL


def months_before(value: datetime, months: int) -> datetime:
    month = value.year * 12 + value.month - 1 - months
    year, month = divmod(month, 12)
    month += 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@contextmanager
def locked(actor: User) -> Iterator[None]:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(74821, 1)")
        operator(actor)
        yield


def maintenance_role() -> None:
    # Runtime can update profiles, but must never erase protected history.
    if settings.APP_ENV == "production":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_has_role(current_user, nspowner, 'USAGE') "
                "FROM pg_namespace WHERE nspname = 'public'"
            )
            result = cursor.fetchone()
        if not result or not result[0]:
            raise PermissionDenied("Utilisez le rôle de maintenance, jamais le runtime web.")


def snapshot() -> str:
    # Streaming digests keep memory bounded, including on populated databases.
    # A concurrent change causes a fresh plan, never an implicit broader apply.
    result = hashlib.sha256()
    for model in sorted(apps.get_models(), key=lambda item: item._meta.label_lower):
        if (
            not model._meta.label_lower.startswith(
                (
                    "identity.",
                    "communities.",
                    "catalogue.",
                    "inventory.",
                    "loans.",
                    "notifications.",
                    "operations.",
                )
            )
            or model._meta.label_lower == "identity.ratebucket"
        ):
            continue
        result.update(model._meta.label_lower.encode())
        for row in model._default_manager.order_by("pk").values().iterator(chunk_size=200):
            result.update(digest(row).encode())
    return result.hexdigest()


def target_user(actor: User, user_id: int) -> User:
    user = User.objects.select_for_update().get(pk=user_id)
    if user.pk == actor.pk or user.is_superuser or user.is_staff or user.email == TOMBSTONE_EMAIL:
        raise ValidationError("Transférez d'abord les fonctions opérateur ; cible protégée.")
    return user


def loans_for(user: User) -> QuerySet[Loan]:
    return Loan.objects.filter(Q(owner=user) | Q(borrower=user))


def inactive(user: User, now: datetime) -> bool:
    return (user.last_login or user.date_joined) <= months_before(now, 12)


def source(user: User, now: datetime) -> str:
    if DeletionRequest.objects.filter(user=user, processed_at__isnull=True).exists():
        return "request"
    notice = InactivityNotice.objects.filter(user=user).first()
    if (
        notice is not None
        and inactive(user, now)
        and notice.sent_at <= now - timedelta(days=30)
        and notice.last_login_at_notice == user.last_login
        and (user.last_login is None or user.last_login <= notice.sent_at)
    ):
        return "inactivity"
    raise ValidationError("Demande ouverte ou préavis d'inactivité de trente jours requis.")


def revoke_sessions(user_id: int) -> None:
    # Django signs session contents; no profile or session token is printed.
    for session in Session.objects.all().iterator(chunk_size=200):
        if str(session.get_decoded().get("_auth_user_id", "")) == str(user_id):
            session.delete()


def discard_outbox(query: Any) -> None:
    # Keep source/event constraints until history is actually removed.
    query.update(
        status=EmailOutbox.Status.DISCARDED,
        encrypted_payload="",
        last_error_code="privacy_erasure",
        completed_at=timezone.now(),
    )


def restrict(actor: User, user: User, now: datetime) -> None:
    if user.deletion_restricted_at is not None:
        return
    user.deletion_restricted_at = now
    user.display_name = "Compte en clôture"
    user.save(update_fields=["deletion_restricted_at", "display_name", "updated_at"])
    OwnedGame.objects.filter(owner=user).update(withdrawn=True)
    OwnedGame.objects.filter(owner=user).exclude(loans__privacy_hold__until__gt=now).update(
        notes=""
    )
    GameVisibility.objects.filter(owned_game__owner=user).delete()
    PendingJoin.objects.filter(user=user).delete()
    archived_copy_ids: set[UUID] = set()
    # A last administrator's community is archived, never assigned without consent.
    for entry in Membership.objects.filter(user=user, active=True).select_related("community"):
        if (
            entry.role == Membership.Role.ADMIN
            and not Membership.objects.filter(
                community=entry.community,
                active=True,
                role=Membership.Role.ADMIN,
                user__is_active=True,
                user__email_verified_at__isnull=False,
                user__deletion_restricted_at__isnull=True,
            )
            .exclude(user=user)
            .exists()
        ):
            archived_copy_ids.update(
                OwnedGame.objects.filter(visibilities__community_id=entry.community_id).values_list(
                    "pk", flat=True
                )
            )
            Community.objects.filter(pk=entry.community_id).update(archived_at=now)
            Membership.objects.filter(community=entry.community).update(active=False)
            GameVisibility.objects.filter(community=entry.community).delete()
            CommunityInvite.objects.filter(community=entry.community).update(
                revoked_at=now, encrypted_token=""
            )
    Membership.objects.filter(user=user).update(active=False, role=Membership.Role.MEMBER)
    CommunityInvite.objects.filter(created_by=user).update(revoked_at=now, encrypted_token="")
    close_ineligible_requests(actor, participant_id=user.pk)
    # Archiving also invalidates other members' still-pending requests in that community.
    for copy_id in archived_copy_ids:
        close_ineligible_requests(actor, copy_id=copy_id)
    pending = loans_for(user).exclude(privacy_hold__until__gt=now)
    LoanEvent.objects.filter(loan__in=pending).update(reason="")
    pending.update(message="", close_reason="")
    Game.objects.filter(created_by=user).update(proposal_reason="")
    GameReport.objects.filter(created_by=user).update(reason="")
    DeletionRequest.objects.filter(user=user).update(reason="")
    AccountToken.objects.filter(user=user).delete()
    discard_outbox(EmailOutbox.objects.filter(recipient=user))
    revoke_sessions(user.pk)
    PrivacyReceipt.objects.create(subject_id=user.pk, action="restrict", created_at=now)


def remove_loans(query: Any) -> int:
    # Explicit order respects PROTECT and retains every accepted/handed-over loan.
    query = query.exclude(state__in=[Loan.State.REQUESTED, *ACTIVE]).exclude(
        privacy_hold__until__gt=timezone.now()
    )
    ids = list(query.values_list("pk", flat=True))
    EmailOutbox.objects.filter(event__loan_id__in=ids).delete()
    LoanEvent.objects.filter(loan_id__in=ids).delete()
    Loan.objects.filter(pk__in=ids).delete()
    return len(ids)


def erase(actor: User, user: User, now: datetime) -> None:
    if (
        loans_for(user)
        .filter(Q(state__in=[Loan.State.REQUESTED, *ACTIVE]) | Q(privacy_hold__until__gt=now))
        .exists()
    ):
        raise ValidationError("Des prêts doivent encore être clôturés ; restriction conservée.")
    # Shared attribution account has no login, token or membership. Account rows
    # and the account-specific graph are removed, not merely renamed.
    tombstone, _ = User.objects.get_or_create(
        email=TOMBSTONE_EMAIL,
        defaults={"display_name": "Compte supprimé", "password": "!", "is_active": False},
    )
    if (
        tombstone.is_active
        or tombstone.has_usable_password()
        or tombstone.is_superuser
        or tombstone.is_staff
    ):
        raise ValidationError("Compte technique d'attribution invalide.")
    remove_loans(loans_for(user))
    OwnedGame.objects.filter(owner=user).delete()
    Game.objects.filter(created_by=user).update(created_by=tombstone, proposal_reason="")
    Community.objects.filter(created_by=user).update(created_by=tombstone)
    CommunityInvite.objects.filter(created_by=user).update(created_by=tombstone)
    InvitationEvent.objects.filter(actor=user).update(actor=tombstone)
    LoanEvent.objects.filter(actor=user).update(actor=tombstone, reason="")
    Membership.objects.filter(user=user).delete()
    GameReport.objects.filter(created_by=user).update(
        created_by=tombstone, reason="", resolved_at=now
    )
    GameDecision.objects.filter(actor=user).update(actor=tombstone, reason="", homonym_reason="")
    GameMerge.objects.filter(actor=user).update(actor=tombstone, reason="")
    from muqola.operations.models import OperatorAction

    OperatorAction.objects.filter(
        Q(operator=user) | Q(target=str(user.pk)) | Q(target__endswith=f":{user.pk}")
    ).update(operator=tombstone, target="", reason="Données personnelles effacées")
    discard_outbox(EmailOutbox.objects.filter(recipient=user))
    EmailOutbox.objects.filter(recipient=user).delete()
    DeletionRequest.objects.filter(user=user).delete()
    revoke_sessions(user.pk)
    PrivacyReceipt.objects.create(subject_id=user.pk, action="erase", created_at=now)
    user.delete()


def candidates(actor: User, after_id: int = 0) -> list[dict[str, Any]]:
    with locked(actor):
        now = timezone.now()
        cutoff = months_before(now, 12)
        query = User.objects.filter(pk__gt=after_id, is_staff=False, is_superuser=False).exclude(
            email=TOMBSTONE_EMAIL
        )
        query = query.filter(
            Q(last_login__lte=cutoff) | Q(last_login__isnull=True, date_joined__lte=cutoff)
        )
        return [
            {
                "user_id": u.pk,
                "notice_sent_at": InactivityNotice.objects.filter(user=u)
                .values_list("sent_at", flat=True)
                .first(),
            }
            for u in query.order_by("pk")[:100]
        ]


def account_operation(
    actor: User,
    user_id: int,
    action: str,
    approved: str = "",
    *,
    review_confirmed: bool = False,
) -> dict[str, Any]:
    with locked(actor):
        if action not in {"notice", "account"}:
            raise ValidationError("Action de compte inconnue.")
        user = target_user(actor, user_id)
        now = timezone.now()
        active_count = loans_for(user).filter(state__in=ACTIVE).count()
        held_count = loans_for(user).filter(privacy_hold__until__gt=now).count()
        if action == "notice":
            if not inactive(user, now):
                raise ValidationError("Compte récemment utilisé : aucun préavis d'inactivité.")
            if InactivityNotice.objects.filter(
                user=user, last_login_at_notice=user.last_login
            ).exists():
                raise ValidationError("Préavis déjà envoyé pour cette période d'inactivité.")
            eligibility = "inactivity_notice"
        else:
            eligibility = source(user, now)
        body = {
            "action": action,
            "user_id": user.pk,
            "source": eligibility,
            "active_loans": active_count,
            "held_loans": held_count,
            "outcome": "notice_queued"
            if action == "notice"
            else ("restricted" if active_count or held_count else "erased"),
            "day": now.date().isoformat(),
            "state": snapshot(),
        }
        key = digest(body)
        result = {
            "plan_hash": key,
            "action": action,
            "user_id": user.pk,
            "active_loans": active_count,
            "held_loans": held_count,
            "outcome": body["outcome"],
            "review_game_ids": list(
                Game.objects.filter(created_by=user).values_list("pk", flat=True)
            ),
            "review_community_ids": list(
                Community.objects.filter(created_by=user).values_list("pk", flat=True)
            ),
            "applied": False,
        }
        if not approved:
            return result
        if approved != key or not review_confirmed:
            raise ValidationError(
                "Plan modifié/périmé ou revue humaine non confirmée : refaire la simulation."
            )
        maintenance_role()
        if action == "notice":
            import secrets

            from muqola.notifications.services import encrypted

            if AccountToken.objects.filter(
                user=user,
                purpose=AccountToken.Purpose.INACTIVITY,
                expires_at__gt=now,
                consumed_at__isnull=True,
            ).exists():
                raise ValidationError("Préavis déjà en file d'envoi.")
            token = AccountToken.objects.create(
                user=user,
                purpose=AccountToken.Purpose.INACTIVITY,
                digest=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                expires_at=now + timedelta(days=7),
            )
            EmailOutbox.objects.create(
                token=token,
                encrypted_payload=encrypted(
                    user.email,
                    "Muqola — votre compte est inactif",
                    "Votre compte Muqola n'a pas été utilisé depuis douze mois. "
                    "Sans nouvelle connexion dans les trente jours suivant ce message, "
                    "l'opérateur pourra engager sa clôture, sous réserve des prêts actifs. "
                    "Connectez-vous pour conserver votre compte : "
                    + settings.APP_BASE_URL
                    + "/accounts/login/",
                ),
            )
            result["outcome"] = "notice_queued"
        else:
            restrict(actor, user, now)
            if not active_count and not held_count:
                erase(actor, user, now)
        result["applied"] = True
        return result


def retention_operation(actor: User, approved: str = "") -> dict[str, Any]:
    with locked(actor):
        now = timezone.now()
        old = (
            Loan.objects.filter(closed_at__lt=months_before(now, 3))
            .exclude(privacy_hold__until__gt=now)
            .exclude(state__in=[Loan.State.REQUESTED, *ACTIVE])
        )
        ids = list(old.order_by("closed_at", "pk").values_list("pk", flat=True)[:100])
        receipts = PrivacyReceipt.objects.filter(created_at__lt=months_before(now, 6))
        result = {
            "action": "retention",
            "loan_count": len(ids),
            "receipt_count": receipts.count(),
            "applied": False,
        }
        key = digest({**result, "loans": ids, "state": snapshot(), "day": now.date()})
        result["plan_hash"] = key
        if not approved:
            return result
        if approved != key:
            raise ValidationError("Plan modifié/périmé : refaire la simulation.")
        maintenance_role()
        remove_loans(Loan.objects.filter(pk__in=ids))
        receipts.delete()
        result["applied"] = True
        return result


def hold_operation(
    actor: User, loan_id: Any, until: datetime, code: str, approved: str = ""
) -> dict[str, Any]:
    with locked(actor):
        now = timezone.now()
        if code not in {"legal", "dispute"} or not now < until <= now + timedelta(days=366):
            raise ValidationError("Exception motivée, bornée à un an avant réexamen, requise.")
        loan = Loan.objects.get(pk=loan_id)
        result = {
            "action": "hold",
            "loan_id": str(loan.pk),
            "until": until,
            "code": code,
            "applied": False,
        }
        key = digest({**result, "day": now.date(), "state": snapshot()})
        result["plan_hash"] = key
        if approved:
            if approved != key:
                raise ValidationError("Plan modifié/périmé : refaire la simulation.")
            maintenance_role()
            PrivacyHold.objects.update_or_create(loan=loan, defaults={"until": until, "code": code})
            result["applied"] = True
        return result


def export_receipts(actor: User) -> str:
    from django.core import signing

    with locked(actor):
        now = timezone.now()
        rows = list(
            PrivacyReceipt.objects.filter(created_at__gte=months_before(now, 6))
            .order_by("pk")
            .values("subject_id", "action")[:10001]
        )
        holds = list(PrivacyHold.objects.filter(until__gt=now).order_by("pk")[:10001])
        if len(rows) > 10000 or len(holds) > 10000:
            raise ValidationError("Export trop volumineux : procédure de sauvegarde à réexaminer.")
        return signing.dumps(
            {
                "origin": settings.APP_BASE_URL,
                "exported_at": now.isoformat(),
                "receipts": rows,
                "holds": [
                    {"loan_id": str(h.loan_id), "until": h.until.isoformat(), "code": h.code}
                    for h in holds
                ],
            },
            salt="muqola.privacy.restore.v1",
            compress=True,
        )


def replay_operation(
    actor: User,
    signed_ledger: str,
    backup_at: datetime,
    approved: str = "",
    *,
    review_confirmed: bool = False,
) -> dict[str, Any]:
    from django.core import signing

    database_name = settings.DATABASES["default"]["NAME"]
    if settings.APP_ENV == "production" and (
        not isinstance(database_name, str) or not database_name.startswith("muqola_restore_")
    ):
        raise ValidationError("Le rejeu exige une base de restauration isolée muqola_restore_*.")
    with locked(actor):
        now = timezone.now()
        try:
            ledger = signing.loads(
                signed_ledger, salt="muqola.privacy.restore.v1", max_age=184 * 86400
            )
            exported = datetime.fromisoformat(ledger["exported_at"])
            if (
                ledger["origin"] != settings.APP_BASE_URL
                or not timezone.is_aware(backup_at)
                or not months_before(now, 6) <= backup_at <= exported <= now
                or exported < now - timedelta(days=1)
                or len(ledger["receipts"]) > 10000
            ):
                raise ValueError
            actions: dict[int, str] = {}
            for row in ledger["receipts"]:
                if row["action"] not in {"restrict", "erase"}:
                    raise ValueError
                key_id = int(row["subject_id"])
                if key_id not in actions or row["action"] == "erase":
                    actions[key_id] = row["action"]
            holds = ledger.get("holds", [])
            if len(holds) > 10000:
                raise ValueError
            for hold in holds:
                if hold["code"] not in {"legal", "dispute"} or timezone.is_naive(
                    datetime.fromisoformat(hold["until"])
                ):
                    raise ValueError
            ids = sorted(actions)
        except (signing.BadSignature, ValueError, TypeError, KeyError) as error:
            raise ValidationError(
                "Preuve signée récente, même origine et sauvegarde de moins de six mois requises."
            ) from error
        targets = list(User.objects.filter(pk__in=ids).order_by("pk"))
        for user in targets:
            target_user(actor, user.pk)
        result = {"action": "replay", "user_ids": [u.pk for u in targets], "applied": False}
        key = digest(
            {
                **result,
                "ledger": digest(signed_ledger),
                "backup_at": backup_at,
                "day": now.date(),
                "state": snapshot(),
            }
        )
        result["plan_hash"] = key
        if not approved:
            return result
        if approved != key or not review_confirmed:
            raise ValidationError(
                "Nouveau plan et confirmation d'un site fermé aux utilisateurs requis."
            )
        maintenance_role()
        for hold in holds:
            until = datetime.fromisoformat(hold["until"])
            if until > now and Loan.objects.filter(pk=hold["loan_id"]).exists():
                existing = PrivacyHold.objects.filter(loan_id=hold["loan_id"]).first()
                if existing is None or existing.until < until:
                    PrivacyHold.objects.update_or_create(
                        loan_id=hold["loan_id"],
                        defaults={
                            "until": until,
                            "code": hold["code"],
                        },
                    )
        blocked = []
        for user in targets:
            restrict(actor, user, now)
            DeletionRequest.objects.get_or_create(user=user)
            if actions[user.pk] != "erase" or (
                loans_for(user)
                .filter(
                    Q(state__in=[Loan.State.REQUESTED, *ACTIVE]) | Q(privacy_hold__until__gt=now)
                )
                .exists()
            ):
                blocked.append(user.pk)
            else:
                erase(actor, user, now)
        result.update(applied=True, loans_to_reconcile=blocked, reopening_allowed=not blocked)
        return result
