"""Outbox durable et chiffrée : SMTP hors des transactions métier."""

import json
import logging
from datetime import timedelta
from smtplib import SMTPException

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from muqola.core.secrets import secret_cipher
from muqola.identity.models import AccountToken, User
from muqola.loans.models import Loan, LoanEvent
from muqola.notifications.models import EmailOutbox

logger = logging.getLogger(__name__)


def cipher() -> Fernet:
    return secret_cipher("email-outbox")


def encrypted(to: str, subject: str, body: str) -> str:
    return (
        cipher().encrypt(json.dumps({"to": to, "subject": subject, "body": body}).encode()).decode()
    )


def enqueue_account_email(token: AccountToken, raw_token: str) -> None:
    action = "verify" if token.purpose == AccountToken.Purpose.VERIFY else "reset"
    subject = (
        "Confirmez votre adresse e-mail"
        if action == "verify"
        else "Réinitialisez votre mot de passe"
    )
    url = f"{settings.APP_BASE_URL}/accounts/{action}/{raw_token}/"
    body = (
        f"{subject} sur Muqola :\n\n{url}\n\n"
        "Ce lien est personnel, temporaire et utilisable une seule fois. "
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message."
    )
    EmailOutbox.objects.create(
        token=token, encrypted_payload=encrypted(token.user.email, subject, body)
    )


def loan_payload(event: LoanEvent, recipient: User) -> str:
    label = Loan.State(event.state).label
    url = f"{settings.APP_BASE_URL}/loans/{event.loan_id}/"
    body = (
        f"Un événement de prêt vous concerne : {label}.\n"
        f"Jeu : {event.loan.owned_game.game.title}\n"
        f"Événement enregistré le {event.created_at.isoformat()} (UTC).\n\n"
        f"Consultez l'état actuel dans votre espace privé :\n{url}\n\n"
        "Les adresses de contact sont accessibles seulement aux parties pendant un prêt actif. "
        "Ce message ne contient aucune adresse de l'autre participant."
    )
    return encrypted(recipient.email, f"Muqola — {label}", body)


def enqueue_loan_event(event: LoanEvent) -> None:
    with transaction.atomic():
        for recipient in (event.loan.owner, event.loan.borrower):
            if recipient.is_active and recipient.email_verified_at:
                EmailOutbox.objects.get_or_create(
                    dedupe_key=f"loan:{event.pk}:{recipient.pk}",
                    defaults={
                        "event": event,
                        "recipient": recipient,
                        "encrypted_payload": loan_payload(event, recipient),
                    },
                )
        LoanEvent.objects.filter(pk=event.pk).update(notifications_queued=True)


def enqueue_pending_events(limit: int = 50) -> int:
    count = 0
    for _ in range(limit):
        with transaction.atomic():
            event = (
                LoanEvent.objects.select_for_update(skip_locked=True)
                .filter(notifications_queued=False)
                .order_by("created_at")
                .first()
            )
            if event is None:
                break
            enqueue_loan_event(event)
            count += 1
    return count


def discard(item: EmailOutbox, code: str) -> None:
    item.status, item.encrypted_payload = EmailOutbox.Status.DISCARDED, ""
    item.last_error_code, item.completed_at = code, timezone.now()


def send_due(limit: int = 20) -> int:
    processed = 0
    for _ in range(limit):
        with transaction.atomic():
            item = (
                EmailOutbox.objects.select_for_update(skip_locked=True)
                .filter(status=EmailOutbox.Status.PENDING, next_attempt_at__lte=timezone.now())
                .order_by("next_attempt_at")
                .first()
            )
            if item is None:
                break
            now = timezone.now()
            invalid = False
            if item.token_id:
                token = AccountToken.objects.select_related("user").get(pk=item.token_id)
                invalid = (
                    token.consumed_at is not None
                    or token.expires_at <= now
                    or not token.user.is_active
                )
            else:
                invalid = (
                    item.recipient_id is None
                    or not User.objects.filter(
                        pk=item.recipient_id, is_active=True, email_verified_at__isnull=False
                    ).exists()
                )
            if invalid:
                discard(item, "recipient_or_token_ineligible")
            else:
                item.attempts += 1
                try:
                    payload = json.loads(cipher().decrypt(item.encrypted_payload.encode()))
                    sent = EmailMessage(
                        payload["subject"],
                        payload["body"],
                        settings.DEFAULT_FROM_EMAIL,
                        [payload["to"]],
                        headers={"Message-ID": f"<{item.pk}@muqola.local>"},
                    ).send(fail_silently=False)
                    if sent != 1:
                        raise OSError("transport_unconfirmed")
                except (SMTPException, OSError, InvalidToken, ValueError, KeyError):
                    item.last_error_code = "transport_or_payload_error"
                    item.next_attempt_at = now + timedelta(
                        seconds=min(3600, 30 * 2 ** min(item.attempts, 7))
                    )
                    if item.attempts >= 20:
                        item.status, item.completed_at = EmailOutbox.Status.FAILED, now
                        logger.error("notification_failed")
                    else:
                        logger.warning("notification_retry")
                else:
                    item.status, item.encrypted_payload = EmailOutbox.Status.SENT, ""
                    item.last_error_code, item.completed_at = "", now
            item.save()
            processed += 1
    return processed


def retry_failed() -> int:
    count = 0
    with transaction.atomic():
        for item in EmailOutbox.objects.select_for_update().filter(
            status=EmailOutbox.Status.FAILED
        ):
            loan_event, recipient = item.event, item.recipient
            if loan_event is not None and recipient is not None:
                item.encrypted_payload = loan_payload(loan_event, recipient)
            if not item.encrypted_payload:
                discard(item, "payload_expired_request_new_link")
            else:
                item.status, item.attempts = EmailOutbox.Status.PENDING, 0
                item.next_attempt_at, item.last_error_code = timezone.now(), ""
                count += 1
            item.save()
    return count


def purge_notifications() -> None:
    now = timezone.now()
    # Échec visible, pas de disparition silencieuse d'un envoi non remis.
    for item in EmailOutbox.objects.filter(
        status=EmailOutbox.Status.PENDING, created_at__lt=now - timedelta(days=7)
    ):
        item.status, item.last_error_code = EmailOutbox.Status.FAILED, "delivery_deadline_exceeded"
        item.completed_at, item.encrypted_payload = now, ""
        item.save()
        logger.error("notification_failed")
    EmailOutbox.objects.filter(
        status=EmailOutbox.Status.FAILED, created_at__lt=now - timedelta(days=7)
    ).update(encrypted_payload="")
    EmailOutbox.objects.exclude(status=EmailOutbox.Status.PENDING).filter(
        completed_at__lt=now - timedelta(days=30)
    ).delete()
    from muqola.communities.models import CommunityInvite, PendingJoin

    CommunityInvite.objects.filter(expires_at__lte=now).update(encrypted_token="")
    PendingJoin.objects.filter(created_at__lt=now - timedelta(days=30)).delete()
