"""Shared security checks with separate, explicit production/staging policies."""

from email.utils import parseaddr
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connection

from muqola.core.legal import documents
from muqola.identity.models import User


def readiness_issues(*, staging: bool = False) -> list[str]:
    issues = []
    if not settings.TRUSTED_PROXY_IPS:
        issues.append("trusted_proxy_not_configured")
    host = urlsplit(settings.APP_BASE_URL).hostname or ""
    if (
        settings.APP_ENV != "production"
        or host.endswith((".test", ".invalid"))
        or host in {"localhost", "127.0.0.1"}
    ):
        issues.append("production_origin_not_configured")
    if set(settings.ALLOWED_HOSTS) != {host}:
        issues.append("hosts_must_match_origin")
    if (
        settings.SECRET_KEY.startswith(("REPLACE", "CHANGE", "build-only"))
        or len(settings.SECRET_KEY) < 50
    ):
        issues.append("django_secret_not_configured")
    if staging:
        if (
            settings.DEPLOYMENT_ENV != "staging"
            or settings.DATABASES["default"]["NAME"] != "muqola_staging"
            or settings.DATABASES["default"]["HOST"] != "db"
            or host != "staging.muqola.tlam.art"
        ):
            issues.append("isolated_staging_required")
        if (
            settings.EMAIL_HOST != "mailpit"
            or settings.EMAIL_PORT != 1025
            or settings.EMAIL_HOST_USER
            or settings.EMAIL_HOST_PASSWORD
            or settings.EMAIL_USE_TLS
            or settings.EMAIL_USE_SSL
            or settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
        ):
            issues.append("staging_capture_required")
        if User.objects.exclude(email__iendswith="@example.test").exists():
            issues.append("staging_requires_fictional_accounts")
    else:
        if settings.DEPLOYMENT_ENV == "staging":
            issues.append("production_deployment_required")
        if (
            not (settings.EMAIL_USE_TLS ^ settings.EMAIL_USE_SSL)
            or settings.EMAIL_HOST in {"localhost", "127.0.0.1", "mailpit"}
            or settings.EMAIL_HOST.endswith((".test", ".invalid"))
        ):
            issues.append("smtp_tls_not_configured")
        if (
            not settings.EMAIL_HOST_USER
            or not settings.EMAIL_HOST_PASSWORD
            or "REPLACE" in settings.EMAIL_HOST_USER
            or "REPLACE" in settings.EMAIL_HOST_PASSWORD
        ):
            issues.append("smtp_credentials_not_configured")
        sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        try:
            validate_email(sender)
        except ValidationError:
            sender = ""
        if (
            not sender
            or sender.rsplit("@", 1)[-1].endswith((".test", ".invalid", ".example"))
            or settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
        ):
            issues.append("smtp_sender_or_backend_not_configured")
    if not documents():
        issues.append("legal_review_required")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user"
        )
        role = cursor.fetchone()
        cursor.execute(
            "SELECT has_database_privilege(current_database(), 'CREATE'), "
            "has_schema_privilege('public', 'CREATE')"
        )
        creation = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relowner="
            "(SELECT oid FROM pg_roles WHERE rolname=current_user)"
        )
        owns = cursor.fetchone()[0]
    if any(role) or any(creation) or owns:
        issues.append("runtime_database_privileges_too_broad")
    # Legacy attestations are enforced per account. Blocking the service here
    # would prevent those users from signing in to attest or closing their loans.
    return issues
