"""Transport SMTP repris en base, limité aux messages de comptes du lot 1."""

import base64
import json
import logging
from datetime import timedelta
from smtplib import SMTPException

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from muqola.identity.models import AccountToken
from muqola.notifications.models import EmailOutbox

logger = logging.getLogger(__name__)


def cipher() -> Fernet:
    key = salted_hmac("muqola.email-outbox", "v1", algorithm="sha256").digest()
    return Fernet(base64.urlsafe_b64encode(key))


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
    payload = json.dumps({"to": token.user.email, "subject": subject, "body": body})
    EmailOutbox.objects.create(
        token=token, encrypted_payload=cipher().encrypt(payload.encode()).decode()
    )


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
            token = AccountToken.objects.select_related("user").get(pk=item.token_id)
            now = timezone.now()
            if token.consumed_at is not None or token.expires_at <= now or not token.user.is_active:
                item.status = EmailOutbox.Status.DISCARDED
            else:
                item.attempts += 1
                try:
                    payload = json.loads(cipher().decrypt(item.encrypted_payload.encode()))
                    EmailMessage(
                        payload["subject"],
                        payload["body"],
                        settings.DEFAULT_FROM_EMAIL,
                        [payload["to"]],
                        headers={"Message-ID": f"<{item.pk}@muqola.local>"},
                    ).send(fail_silently=False)
                except (SMTPException, OSError, InvalidToken, ValueError, KeyError):
                    item.next_attempt_at = now + timedelta(
                        seconds=min(3600, 30 * 2 ** min(item.attempts, 7))
                    )
                    logger.warning("account_email_retry")
                else:
                    item.status = EmailOutbox.Status.SENT
            if item.status != EmailOutbox.Status.PENDING:
                item.encrypted_payload = ""
                item.completed_at = now
            item.save()
            processed += 1
    return processed
