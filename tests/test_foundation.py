import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, override_settings

from muqola.core.logging import SafeJsonFormatter
from muqola.identity.models import User


def test_public_home_is_french_and_discloses_current_scope(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b'lang="fr"' in response.content
    assert "Les comptes sont ouverts" in response.content.decode()
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert "default-src 'none'" in response["Content-Security-Policy"]
    assert response["X-Content-Type-Options"] == "nosniff"


def test_live_does_not_access_database(client: Client) -> None:
    with patch("muqola.core.views.connection.cursor", side_effect=AssertionError("DB accessed")):
        assert client.get("/health/live/").json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_checks_real_postgres_and_migrations(client: Client) -> None:
    assert connection.vendor == "postgresql"
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert client.get("/health/ready/").json() == {"status": "ok"}


def test_ready_failure_does_not_leak_database_credentials(client: Client) -> None:
    with patch("muqola.core.views.connection.cursor", side_effect=DatabaseError("secret-value")):
        response = client.get("/health/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"secret-value" not in response.content


@pytest.mark.django_db
def test_custom_user_and_database_sessions() -> None:
    user = User.objects.create_user(
        "  Alice@Example.test ", "synthetic-password", display_name="Alice"
    )
    assert User.objects.get(email="alice@example.test").pk == user.pk
    assert user.check_password("synthetic-password")
    assert user.email_verified_at is None
    session = SessionStore()
    session["synthetic"] = user.pk
    session.save()
    assert SessionStore(session.session_key)["synthetic"] == user.pk


@pytest.mark.parametrize("path", ["/admin/", "/communities/", "/games/", "/loans/"])
def test_no_business_routes_are_exposed(client: Client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert "Page introuvable" in response.content.decode()


@override_settings(
    APP_ENV="production",
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
)
def test_production_uses_secure_transport(client: Client) -> None:
    assert client.get("/").status_code == 301
    assert client.get("/", secure=True).status_code == 200
    assert settings.SESSION_COOKIE_SECURE
    assert settings.CSRF_COOKIE_SECURE


def test_logs_drop_urls_tokens_and_exceptions() -> None:
    record = logging.LogRecord(
        "django.request", logging.ERROR, "", 1, "/invite/?token=secret-value", (), None
    )
    output = SafeJsonFormatter().format(record)
    assert "secret-value" not in output
    assert json.loads(output)["event"] == "runtime_event"


@override_settings(
    APP_ENV="development",
    EMAIL_HOST="mailpit",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_dev_email_uses_synthetic_recipient() -> None:
    from django.core import mail

    call_command("send_dev_email", stdout=StringIO())
    assert mail.outbox[-1].to == ["test@example.test"]


@pytest.mark.parametrize(
    "env,host,recipient",
    [
        ("production", "mailpit", "test@example.test"),
        ("development", "smtp.example.org", "test@example.test"),
        ("development", "mailpit", "real@example.org"),
    ],
)
def test_dev_email_refuses_real_transport(env: str, host: str, recipient: str) -> None:
    with override_settings(APP_ENV=env, EMAIL_HOST=host), pytest.raises(CommandError):
        call_command("send_dev_email", to=recipient)
