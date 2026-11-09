import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from muqola.identity.models import AccountToken, RateBucket, User
from muqola.notifications.services import enqueue_account_email


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(user: User, purpose: str) -> None:
    # Appel dans une transaction verrouillant déjà l'utilisateur.
    now = timezone.now()
    AccountToken.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(
        consumed_at=now
    )
    raw = secrets.token_urlsafe(32)
    token = AccountToken.objects.create(
        user=user,
        purpose=purpose,
        digest=token_digest(raw),
        expires_at=now + timedelta(hours=24 if purpose == AccountToken.Purpose.VERIFY else 1),
    )
    enqueue_account_email(token, raw)


def register(email: str, display_name: str, password: str) -> None:
    # Même travail cryptographique et même réponse pour une adresse déjà inscrite.
    password_hash = make_password(password)
    try:
        with transaction.atomic():
            user = User.objects.create(
                email=email, display_name=display_name, password=password_hash
            )
            issue_token(user, AccountToken.Purpose.VERIFY)
    except IntegrityError:
        # Seul le doublon attendu est neutralisé ; les autres erreurs remontent.
        if not User.objects.filter(email=email).exists():
            raise


def request_token(email: str, purpose: str) -> None:
    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=email, is_active=True).first()
        if user is None or (purpose == AccountToken.Purpose.VERIFY and user.email_verified_at):
            return
        issue_token(user, purpose)


def usable_token(digest: str, purpose: str) -> AccountToken | None:
    return (
        AccountToken.objects.select_related("user")
        .filter(
            digest=digest,
            purpose=purpose,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        )
        .first()
    )


def consume_token(digest: str, purpose: str, password: str | None = None) -> bool:
    candidate = usable_token(digest, purpose)
    if candidate is None:
        return False
    with transaction.atomic():
        # Ordre commun à émission et consommation : utilisateur puis jeton.
        user = User.objects.select_for_update().get(pk=candidate.user_id)
        token = AccountToken.objects.select_for_update().get(pk=candidate.pk)
        now = timezone.now()
        if not user.is_active or token.consumed_at is not None or token.expires_at <= now:
            return False
        if purpose == AccountToken.Purpose.VERIFY:
            user.email_verified_at = now
        elif password is not None:
            user.set_password(password)
        else:
            return False
        user.save()
        tokens = AccountToken.objects.filter(user=user, consumed_at__isnull=True)
        if purpose == AccountToken.Purpose.VERIFY:
            tokens = tokens.filter(purpose=purpose)
        tokens.update(consumed_at=now)
        return True


def purge_ephemeral_data() -> None:
    now = timezone.now()
    RateBucket.objects.filter(expires_at__lt=now).delete()
    # Petite marge de diagnostic, aucun jeton de compte conservé indéfiniment.
    cutoff = now - timedelta(days=1)
    AccountToken.objects.filter(expires_at__lt=cutoff).delete()
    AccountToken.objects.filter(consumed_at__lt=cutoff).delete()
