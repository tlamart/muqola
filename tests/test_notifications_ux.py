import json
import runpy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Lock
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from muqola.catalogue.models import Game
from muqola.inventory.models import OwnedGame
from muqola.loans import services as loans
from muqola.loans.models import LoanEvent
from muqola.notifications import services
from muqola.notifications.models import EmailOutbox
from muqola.operations import services as operations
from muqola.operations.models import DeletionRequest, OperatorAction
from tests.helpers import member
from tests.test_loans import scenario

pytestmark = pytest.mark.django_db


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_every_state_has_private_deduplicated_transactional_notifications() -> None:
    alice, bob, _, _, copy = scenario()
    due = loans.today() + timedelta(days=7)
    for actions in (("accept", "handover", "return"), ("decline",), ("cancel",)):
        loan = loans.request_loan(bob, copy.pk, due, "Texte privé à exclure")
        for action in actions:
            loans.transition(alice, loan.pk, action)
    assert set(LoanEvent.objects.values_list("state", flat=True)) == {
        "REQUESTED",
        "ACCEPTED",
        "HANDED_OVER",
        "RETURNED",
        "DECLINED",
        "CANCELLED",
    }
    expected = LoanEvent.objects.count() * 2
    for event in LoanEvent.objects.all():
        services.enqueue_loan_event(event)
    assert EmailOutbox.objects.count() == expected
    assert not LoanEvent.objects.filter(notifications_queued=False).exists()
    for item in EmailOutbox.objects.select_related("recipient", "event"):
        payload = json.loads(services.cipher().decrypt(item.encrypted_payload.encode()))
        assert item.event is not None and item.recipient is not None
        other = bob if item.recipient_id == alice.pk else alice
        assert other.email not in payload["body"]
        assert "Texte privé" not in payload["body"]
        assert f"/loans/{item.event.loan_id}/" in payload["body"]
        assert item.recipient.email not in item.encrypted_payload
    assert services.send_due(limit=50) == expected
    assert len(mail.outbox) == expected
    assert services.send_due(limit=50) == 0
    assert not EmailOutbox.objects.exclude(encrypted_payload="").exists()


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_transport_failure_preserves_loan_and_recovers_after_restart() -> None:
    alice, bob, _, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    with patch("muqola.notifications.services.EmailMessage.send", side_effect=OSError):
        assert services.send_due() == 4
    loan.refresh_from_db()
    assert loan.state == "ACCEPTED"
    assert EmailOutbox.objects.filter(status="pending", attempts=1).count() == 4
    assert services.send_due() == 0  # Backoff persistant, pas de boucle SMTP serrée.
    EmailOutbox.objects.update(next_attempt_at=timezone.now())
    call_command("process_outbox", once=True, stdout=StringIO())
    assert EmailOutbox.objects.filter(status="sent").count() == 4


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_exhausted_delivery_is_visible_and_manual_retry_can_regenerate_payload() -> None:
    _, bob, _, _, copy = scenario()
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    EmailOutbox.objects.update(attempts=19)
    with patch("muqola.notifications.services.EmailMessage.send", side_effect=OSError):
        services.send_due()
    assert EmailOutbox.objects.filter(status="failed", attempts=20).count() == 2
    EmailOutbox.objects.update(created_at=timezone.now() - timedelta(days=8))
    services.purge_notifications()
    assert not EmailOutbox.objects.exclude(encrypted_payload="").exists()
    assert services.retry_failed() == 2
    assert services.send_due() == 2
    assert EmailOutbox.objects.filter(status="sent").count() == 2


def test_retention_does_not_silently_drop_pending_notifications() -> None:
    _, bob, _, _, copy = scenario()
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    EmailOutbox.objects.update(created_at=timezone.now() - timedelta(days=8))
    services.purge_notifications()
    assert (
        EmailOutbox.objects.filter(
            status="failed", last_error_code="delivery_deadline_exceeded", encrypted_payload=""
        ).count()
        == 2
    )
    EmailOutbox.objects.update(completed_at=timezone.now() - timedelta(days=31))
    services.purge_notifications()
    assert EmailOutbox.objects.count() == 0
    assert LoanEvent.objects.count() == 1


def test_disabled_recipient_is_discarded_and_unqueued_events_recovered() -> None:
    alice, bob, _, _, copy = scenario()
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    EmailOutbox.objects.all().delete()
    LoanEvent.objects.update(notifications_queued=False)
    assert services.enqueue_pending_events() == 1
    assert services.enqueue_pending_events() == 0
    bob.is_active = False
    bob.save()
    with patch("muqola.notifications.services.EmailMessage.send", return_value=1):
        services.send_due()
    assert EmailOutbox.objects.get(recipient=bob).status == "discarded"
    assert EmailOutbox.objects.get(recipient=alice).status == "sent"


def test_rolled_back_business_event_has_no_notification() -> None:
    _, bob, _, _, copy = scenario()
    with pytest.raises(ValidationError), transaction.atomic():
        loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
        raise ValidationError("Annulation de transaction")
    assert not LoanEvent.objects.exists() and not EmailOutbox.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_parallel_workers_do_not_send_the_same_row_twice() -> None:
    _, bob, _, _, copy = scenario()
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    barrier, lock = Barrier(2), Lock()
    ids: list[str] = []

    def deliver(message: mail.EmailMessage, **kwargs: object) -> int:
        with lock:
            ids.append(message.extra_headers["Message-ID"])
        return 1

    def worker(_: int) -> int:
        try:
            barrier.wait(timeout=10)
            return services.send_due()
        finally:
            connections.close_all()

    with patch("muqola.notifications.services.EmailMessage.send", new=deliver):
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(worker, [1, 2])) == 2
    assert len(ids) == len(set(ids)) == 2
    assert EmailOutbox.objects.filter(status="sent").count() == 2


def test_operator_permissions_audit_and_preservation_of_active_loan() -> None:
    alice, bob, _, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    with pytest.raises(PermissionDenied):
        operations.disable_user(alice, bob.pk, "Sécurité")
    operator = member("Operateur")
    operator.is_superuser = True
    operator.save()
    with pytest.raises(ValidationError):
        operations.moderate_game(operator, copy.game_id, "")
    operations.moderate_game(operator, copy.game_id, "Fiche signalée")
    copy.refresh_from_db()
    loan.refresh_from_db()
    assert copy.withdrawn and loan.state == "ACCEPTED"
    assert OperatorAction.objects.get().action == "hide_game"
    operations.disable_user(operator, bob.pk, "Compte abusif")
    bob.refresh_from_db()
    assert not bob.is_active
    loans.resolve(operator, loan.pk, "CANCELLED", "Résolution avant remise")
    loan.refresh_from_db()
    assert loan.state == "CANCELLED"
    with pytest.raises(CommandError):
        call_command("ops", "outbox-status", operator=alice.email, stdout=StringIO())
    output = StringIO()
    call_command("ops", "outbox-status", operator=operator.email, stdout=output)
    assert "count" in output.getvalue() and bob.email not in output.getvalue()
    call_command("ops", "retry-failed", operator=operator.email, stdout=StringIO())
    assert OperatorAction.objects.filter(action="retry_notifications", operator=operator).exists()


def test_profile_deletion_is_own_confirmed_request_and_preserves_active_loans(
    client: Client,
) -> None:
    alice, bob, _, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    client.force_login(bob)
    url = reverse("identity:profile")
    assert "prêt actif" in client.get(url).content.decode()
    client.post(url, {"reason": "Départ", "user_id": alice.pk})
    assert not DeletionRequest.objects.exists()
    assert client.post(url, {"confirm": "on", "reason": "Départ"}).status_code == 302
    assert DeletionRequest.objects.get().user_id == bob.pk
    operations.request_deletion(bob, "Précision")
    assert DeletionRequest.objects.count() == 1
    loan.refresh_from_db()
    assert loan.state == "ACCEPTED"
    bob.refresh_from_db()
    assert bob.is_active


def test_empty_dashboard_and_paginated_private_collection(client: Client) -> None:
    user = member()
    client.force_login(user)
    response = client.get(reverse("identity:dashboard"))
    assert "aucune communauté" in response.content.decode().lower()
    game = Game.objects.create(title="Jeu", title_key="jeu", created_by=user)
    OwnedGame.objects.bulk_create([OwnedGame(owner=user, game=game) for _ in range(31)])
    url = reverse("inventory:mine")
    assert len(client.get(url).context["copies"]) == 30
    response = client.get(url + "?page=2")
    assert len(response.context["copies"]) == 1
    assert "Page précédente" in response.content.decode()


@pytest.mark.parametrize(
    "overrides",
    [
        {"EMAIL_HOST": "smtp.example.test"},
        {"EMAIL_HOST_USER": "fictif"},
        {"EMAIL_HOST_PASSWORD": "mot-de-passe-fictif"},
        {"EMAIL_USE_TLS": "true", "EMAIL_USE_SSL": "true"},
    ],
)
def test_development_refuses_external_smtp_or_incompatible_tls(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    for key, value in {
        "APP_ENV": "development",
        "EMAIL_HOST": "mailpit",
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
        "EMAIL_USE_TLS": "false",
        "EMAIL_USE_SSL": "false",
        **overrides,
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ImproperlyConfigured):
        runpy.run_path("config/settings.py")
