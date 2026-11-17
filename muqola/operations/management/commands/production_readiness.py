"""Explicit launch gate; configuration checks are not proof of public TLS or delivery."""

import json
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection

from muqola.core.legal import documents
from muqola.identity.models import User


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        issues = []
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
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname=current_user"
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
        if User.objects.filter(is_active=True, adult_confirmed_at__isnull=True).exists():
            issues.append("existing_accounts_need_adult_confirmation")
        self.stdout.write(json.dumps({"ready_for_launch": not issues, "issues": issues}))
        if issues:
            raise CommandError("Préparation incomplète ; voir les codes sans secrets ci-dessus.")
