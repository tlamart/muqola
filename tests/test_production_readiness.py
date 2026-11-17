"""Safety gates are executable; legal/SMTP/live infrastructure remain human gates."""

from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.management import CommandError, call_command
from django.test import Client, override_settings
from django.urls import reverse

from config.env import secret
from muqola.core.legal import DOCUMENTS, documents
from muqola.core.transactions import verified
from muqola.identity.models import User
from muqola.identity.services import register
from muqola.inventory.services import borrowable, write_copy
from muqola.loans import services as loans
from muqola.notifications.models import EmailOutbox
from tests.helpers import member
from tests.test_loans import scenario

pytestmark = pytest.mark.django_db


def test_secret_files_fail_closed_without_disclosing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "secret"
    path.write_text("synthetic-private-value\n")
    monkeypatch.setenv("EXAMPLE_SECRET_FILE", str(path))
    assert secret("EXAMPLE_SECRET") == "synthetic-private-value"
    monkeypatch.setenv("EXAMPLE_SECRET", "other-private-value")
    with pytest.raises(ImproperlyConfigured) as error:
        secret("EXAMPLE_SECRET")
    assert "private-value" not in str(error.value)
    monkeypatch.delenv("EXAMPLE_SECRET")
    path.unlink()
    with pytest.raises(ImproperlyConfigured):
        secret("EXAMPLE_SECRET")


def test_signup_requires_explicit_adult_attestation_server_side(client: Client) -> None:
    payload = {
        "email": "adult@example.test",
        "display_name": "Adulte",
        "password": "Synthetic-long-password-2026!",
        "password_confirm": "Synthetic-long-password-2026!",
    }
    response = client.post(reverse("identity:signup"), payload)
    assert response.status_code == 200 and not User.objects.exists()
    assert not EmailOutbox.objects.exists()
    with pytest.raises(ValidationError):
        register(payload["email"], payload["display_name"], payload["password"])
    response = client.post(reverse("identity:signup"), payload | {"adult_confirmed": "on"})
    assert response.status_code == 302
    assert User.objects.get().adult_confirmed_at is not None


def test_legacy_account_requires_attestation_but_can_close_existing_loan(client: Client) -> None:
    owner, reader, _, _, item = scenario()
    loan = loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
    loans.transition(owner, loan.pk, "accept")
    User.objects.filter(pk=owner.pk).update(adult_confirmed_at=None)
    owner.refresh_from_db()
    with pytest.raises(PermissionDenied):
        write_copy(owner, item.game_id, "", [])
    assert not borrowable(reader).exists()
    client.force_login(owner)
    assert client.get(reverse("inventory:index"))["Location"] == reverse("identity:adult")
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 200
    assert client.get(reverse("identity:profile")).status_code == 200
    assert client.post(reverse("identity:profile"), {"confirm": "on"}).status_code == 302
    from muqola.operations.models import DeletionRequest

    assert DeletionRequest.objects.filter(user=owner).exists()
    loans.transition(owner, loan.pk, "handover")
    loans.transition(owner, loan.pk, "return")
    assert client.post(reverse("identity:adult"), {}).status_code == 200
    assert User.objects.get(pk=owner.pk).adult_confirmed_at is None
    assert client.post(reverse("identity:adult"), {"adult_confirmed": "on"}).status_code == 302
    owner.refresh_from_db()
    verified(owner)


def test_unattested_borrower_cannot_start_or_accept_new_loan(client: Client) -> None:
    owner, reader, _, _, item = scenario()
    loan = loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
    User.objects.filter(pk=reader.pk).update(adult_confirmed_at=None)
    reader.refresh_from_db()
    with pytest.raises(PermissionDenied):
        loans.request_loan(reader, item.pk, loan.due_date)
    with pytest.raises(ValidationError):
        loans.transition(owner, loan.pk, "accept")
    loans.transition(reader, loan.pk, "cancel")


def test_legal_pages_are_public_but_placeholders_are_not_published(
    client: Client, tmp_path: Path
) -> None:
    with override_settings(LEGAL_DOCUMENTS_DIR=tmp_path, LEGAL_REVIEWED=True):
        for key, (_, filename) in DOCUMENTS.items():
            (tmp_path / filename).write_text("[À RENSEIGNER : identité réelle]")
            response = client.get(reverse("legal", args=[key]))
            assert response.status_code == 503
            assert "identité réelle" not in response.content.decode()
        for _, filename in DOCUMENTS.values():
            (tmp_path / filename).write_text(
                "Validation synthétique, pas une information juridique réelle. "
                "<script>alert(1)</script>"
            )
        assert len(documents()) == 4
        response = client.get(reverse("legal", args=["terms"]))
        assert response.status_code == 200 and b"<script>" not in response.content
        assert b"&lt;script&gt;" in response.content
    assert client.get(reverse("legal", args=["absent"])).status_code == 404


def test_production_signup_is_closed_until_legal_review(client: Client, tmp_path: Path) -> None:
    with override_settings(
        APP_ENV="production", LEGAL_DOCUMENTS_DIR=tmp_path, LEGAL_REVIEWED=False
    ):
        assert client.get(reverse("identity:signup")).status_code == 503
        assert not User.objects.exists()


def test_readiness_reports_codes_not_credentials() -> None:
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("production_readiness", stdout=output)
    report = output.getvalue()
    assert "runtime_database_privileges_too_broad" in report
    assert "legal_review_required" in report
    assert "password" not in report and "@example.test" not in report


@pytest.mark.django_db(transaction=True)
def test_worker_heartbeat_and_private_aggregate_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat"
    call_command("process_outbox", once=True, heartbeat_file=path, stdout=StringIO())
    assert path.is_file()
    member()
    output = StringIO()
    call_command("check_operations", stdout=output)
    assert '"database": true' in output.getvalue()
    assert "alice@example.test" not in output.getvalue()
