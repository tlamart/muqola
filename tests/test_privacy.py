import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections
from django.http import Http404
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from muqola.catalogue.models import Game
from muqola.communities import services as communities
from muqola.communities.models import Community, Membership
from muqola.identity.models import AccountToken, User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.loans import services as loans
from muqola.loans.models import Loan, LoanEvent
from muqola.notifications.models import EmailOutbox
from muqola.operations import privacy
from muqola.operations.models import InactivityNotice, PrivacyHold, PrivacyReceipt
from muqola.operations.services import request_deletion
from tests.helpers import catalogue_operator, member
from tests.test_loans import scenario

pytestmark = pytest.mark.django_db


def apply_account(actor: User, user: User) -> dict[str, object]:
    plan = privacy.account_operation(actor, user.pk, "account")
    return privacy.account_operation(
        actor, user.pk, "account", plan["plan_hash"], review_confirmed=True
    )


def test_plan_does_not_change_or_print_personal_data() -> None:
    alice, _, _, _, _ = scenario()
    request_deletion(alice, "Une précision privée")
    before = privacy.snapshot()
    plan = privacy.account_operation(catalogue_operator(), alice.pk, "account")
    assert not plan["applied"] and plan["outcome"] == "erased"
    assert privacy.snapshot() == before
    assert alice.email not in json.dumps(plan, default=str)
    assert "précision" not in json.dumps(plan, default=str)


@pytest.mark.parametrize("kind", ["regular", "unverified", "inactive", "restricted"])
def test_operator_guard(kind: str) -> None:
    user = member()
    request_deletion(user)
    actor = member("Operateur", verified=kind != "unverified")
    actor.is_superuser = kind != "regular"
    actor.is_active = kind != "inactive"
    actor.deletion_restricted_at = timezone.now() if kind == "restricted" else None
    actor.save()
    with pytest.raises(PermissionDenied):
        privacy.account_operation(actor, user.pk, "account")


def test_request_and_explicit_review_required() -> None:
    user = member()
    op = catalogue_operator()
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account")
    request_deletion(user)
    plan = privacy.account_operation(op, user.pk, "account")
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account", plan["plan_hash"])
    user.display_name = "Modification depuis la simulation"
    user.save()
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account", plan["plan_hash"], review_confirmed=True)
    assert User.objects.filter(pk=user.pk).exists()


def test_erasure_preserves_shared_catalogue_and_other_members() -> None:
    alice, bob, clara, community, copy = scenario()
    Membership.objects.filter(user=bob, community=community).update(role=Membership.Role.ADMIN)
    own_other = OwnedGame.objects.create(game=copy.game, owner=bob, notes="Notes de Bob")
    old_user_id, game_id, community_id = alice.pk, copy.game_id, community.pk
    request_deletion(alice)
    client = Client()
    client.force_login(alice)
    assert Session.objects.count() == 1
    apply_account(catalogue_operator(), alice)
    assert not User.objects.filter(pk=old_user_id).exists()
    assert Game.objects.filter(pk=game_id).exists()
    assert Community.objects.get(pk=community_id).archived_at is None
    assert Membership.objects.filter(user=bob, active=True).exists()
    own_other.refresh_from_db()
    assert own_other.notes == "Notes de Bob"
    assert User.objects.filter(pk=clara.pk).exists()
    assert not Session.objects.exists()
    assert PrivacyReceipt.objects.filter(subject_id=old_user_id, action="erase").exists()
    tombstone = User.objects.get(email=privacy.TOMBSTONE_EMAIL)
    assert not tombstone.is_active and not tombstone.has_usable_password()
    assert Game.objects.get(pk=game_id).created_by == tombstone


@pytest.mark.parametrize("state", [Loan.State.ACCEPTED, Loan.State.HANDED_OVER])
def test_restriction_preserves_closure_and_blocks_new_access(state: str, client: Client) -> None:
    alice, bob, _, community, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7), "Message privé")
    loans.transition(alice, loan.pk, "accept")
    if state == Loan.State.HANDED_OVER:
        loans.transition(alice, loan.pk, "handover")
    request_deletion(alice)
    plan = apply_account(catalogue_operator(), alice)
    alice.refresh_from_db()
    assert plan["outcome"] == "restricted" and alice.is_active
    assert alice.deletion_restricted_at is not None
    loan.refresh_from_db()
    copy.refresh_from_db()
    assert loan.state == state and loan.message == "" and copy.notes == ""
    assert not GameVisibility.objects.filter(owned_game=copy).exists()
    assert Community.objects.get(pk=community.pk).archived_at is not None
    with pytest.raises(PermissionDenied):
        communities.create(alice, "Interdit")
    with pytest.raises(PermissionDenied):
        loans.request_loan(alice, copy.pk, loans.today() + timedelta(days=2))
    contacts = loans.contacts(bob, loan.pk)
    assert contacts is not None and contacts["owner"] == alice.email
    client.force_login(alice)
    assert client.get(reverse("identity:profile")).status_code == 200
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 200
    assert client.get(reverse("communities:index")).status_code == 302
    if state == Loan.State.ACCEPTED:
        loans.transition(alice, loan.pk, "handover")
    loans.transition(alice, loan.pk, "return")
    assert loans.contacts(bob, loan.pk) is None
    apply_account(catalogue_operator(), alice)
    assert not User.objects.filter(pk=alice.pk).exists()
    assert not Loan.objects.filter(pk=loan.pk).exists()
    assert not LoanEvent.objects.filter(loan_id=loan.pk).exists()
    assert not EmailOutbox.objects.filter(event__loan_id=loan.pk).exists()


def test_restricted_borrower_and_requested_cancellation() -> None:
    alice, bob, clara, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    second = OwnedGame.objects.create(game=copy.game, owner=clara)
    request_deletion(bob)
    apply_account(catalogue_operator(), bob)
    with pytest.raises(PermissionDenied):
        loans.request_loan(bob, second.pk, loans.today() + timedelta(days=3))
    loans.transition(bob, loan.pk, "cancel")
    apply_account(catalogue_operator(), bob)
    assert not User.objects.filter(pk=bob.pk).exists()
    assert User.objects.filter(pk=alice.pk).exists()


def test_archive_revokes_invitation_and_cross_community_stays_private() -> None:
    alice, bob, clara, community, copy = scenario()
    invitation = communities.invite(alice, community.pk)
    other = communities.create(clara, "Autres")
    request_deletion(alice)
    apply_account(catalogue_operator(), alice)
    invitation.refresh_from_db()
    assert invitation.revoked_at is not None and invitation.encrypted_token == ""
    assert communities.valid_invite(invitation.digest) is None
    assert communities.membership(clara, other.pk).active
    assert not Membership.objects.filter(community=community, active=True).exists()
    assert not OwnedGame.objects.filter(pk=copy.pk).exists()


def test_erasure_is_atomic_on_unknown_reference() -> None:
    user = member()
    request_deletion(user)
    op = catalogue_operator()
    plan = privacy.account_operation(op, user.pk, "account")
    with patch.object(User, "delete", side_effect=RuntimeError("synthetic failure")):
        with pytest.raises(RuntimeError):
            privacy.account_operation(
                op, user.pk, "account", plan["plan_hash"], review_confirmed=True
            )
    user.refresh_from_db()
    assert user.deletion_restricted_at is None
    assert not PrivacyReceipt.objects.exists()


def test_inactivity_requires_real_notice_and_new_login_cancels_eligibility() -> None:
    user = member()
    now = timezone.now()
    User.objects.filter(pk=user.pk).update(date_joined=privacy.months_before(now, 13))
    user.refresh_from_db()
    op = catalogue_operator()
    assert privacy.candidates(op)[0]["user_id"] == user.pk
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account")
    plan = privacy.account_operation(op, user.pk, "notice")
    privacy.account_operation(op, user.pk, "notice", plan["plan_hash"], review_confirmed=True)
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account")
    from muqola.notifications.services import send_due

    assert not InactivityNotice.objects.filter(user=user).exists()
    assert send_due() == 1
    assert InactivityNotice.objects.filter(user=user).exists()
    InactivityNotice.objects.filter(user=user).update(sent_at=now - timedelta(days=31))
    assert privacy.account_operation(op, user.pk, "account")["outcome"] == "erased"
    User.objects.filter(pk=user.pk).update(last_login=now)
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account")


def test_calendar_months_not_ninety_days() -> None:
    now = timezone.now().replace(year=2026, month=5, day=31)
    assert privacy.months_before(now, 3).date().isoformat() == "2026-02-28"


def test_retention_removes_only_terminal_old_loans_and_six_month_receipts() -> None:
    alice, bob, _, _, copy = scenario()
    old = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, old.pk, "decline")
    Loan.objects.filter(pk=old.pk).update(closed_at=privacy.months_before(timezone.now(), 4))
    live = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=8))
    loans.transition(alice, live.pk, "accept")
    Loan.objects.filter(pk=live.pk).update(closed_at=privacy.months_before(timezone.now(), 4))
    PrivacyReceipt.objects.create(
        subject_id=999, action="erase", created_at=privacy.months_before(timezone.now(), 7)
    )
    PrivacyReceipt.objects.create(subject_id=998, action="erase", created_at=timezone.now())
    op = catalogue_operator()
    plan = privacy.retention_operation(op)
    assert plan["loan_count"] == 1 and plan["receipt_count"] == 1
    privacy.retention_operation(op, plan["plan_hash"])
    assert not Loan.objects.filter(pk=old.pk).exists()
    assert Loan.objects.filter(pk=live.pk).exists()
    assert PrivacyReceipt.objects.count() == 1


def test_hold_blocks_history_cleanup_and_final_erasure_until_expiry() -> None:
    alice, bob, _, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7), "Preuve du litige")
    loans.transition(alice, loan.pk, "decline")
    Loan.objects.filter(pk=loan.pk).update(closed_at=privacy.months_before(timezone.now(), 4))
    op = catalogue_operator()
    until = timezone.now() + timedelta(days=3)
    plan = privacy.hold_operation(op, loan.pk, until, "dispute")
    privacy.hold_operation(op, loan.pk, until, "dispute", plan["plan_hash"])
    assert privacy.retention_operation(op)["loan_count"] == 0
    request_deletion(bob)
    assert apply_account(op, bob)["outcome"] == "restricted"
    loan.refresh_from_db()
    assert loan.message == "Preuve du litige"
    PrivacyHold.objects.filter(loan=loan).update(until=timezone.now() - timedelta(seconds=1))
    apply_account(op, bob)
    assert not User.objects.filter(pk=bob.pk).exists()


def test_cli_requires_operator_and_does_not_leak_email() -> None:
    user = member()
    request_deletion(user)
    op = catalogue_operator()
    output = StringIO()
    call_command("privacy", "account", operator_id=op.pk, user_id=user.pk, stdout=output)
    assert user.email not in output.getvalue()
    assert not json.loads(output.getvalue())["applied"]
    with pytest.raises(CommandError):
        call_command("privacy", "account", operator_id=user.pk, user_id=user.pk)


def test_runtime_cannot_apply_in_production() -> None:
    op, user = catalogue_operator(), member()
    request_deletion(user)
    with override_settings(APP_ENV="production"):
        with patch.object(privacy, "maintenance_role", side_effect=PermissionDenied):
            plan = privacy.account_operation(op, user.pk, "account")
            with pytest.raises(PermissionDenied):
                privacy.account_operation(
                    op, user.pk, "account", plan["plan_hash"], review_confirmed=True
                )
    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_worker_purges_expired_sessions_but_keeps_current(client: Client) -> None:
    user = member()
    client.force_login(user)
    Session.objects.create(
        session_key="expired-synthetic",
        session_data="",
        expire_date=timezone.now() - timedelta(days=1),
    )
    call_command("process_outbox", once=True)
    assert not Session.objects.filter(session_key="expired-synthetic").exists()
    assert Session.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_request_acceptance_racing_erasure_has_no_dangling_or_active_deleted_user() -> None:
    alice, bob, _, _, copy = scenario()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=3))
    request_deletion(bob)
    op = catalogue_operator()
    plan = privacy.account_operation(op, bob.pk, "account")
    barrier = Barrier(2)

    def work(action: str) -> None:
        connections.close_all()
        barrier.wait(timeout=10)
        try:
            if action == "erase":
                privacy.account_operation(
                    User.objects.get(pk=op.pk),
                    bob.pk,
                    "account",
                    plan["plan_hash"],
                    review_confirmed=True,
                )
            else:
                loans.transition(User.objects.get(pk=alice.pk), loan.pk, "accept")
        except (ValidationError, PermissionDenied, User.DoesNotExist, Http404):
            pass
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(work, ["erase", "accept"]))
    if User.objects.filter(pk=bob.pk).exists():
        assert Loan.objects.filter(pk=loan.pk, state=Loan.State.ACCEPTED).exists()
    else:
        assert not Loan.objects.filter(pk=loan.pk).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM loans_loan l LEFT JOIN identity_user u "
            "ON u.id=l.borrower_id WHERE u.id IS NULL"
        )
        assert cursor.fetchone()[0] == 0


def test_notice_delivery_failure_never_starts_thirty_day_clock() -> None:
    from muqola.notifications.services import send_due

    op, user = catalogue_operator(), member()
    User.objects.filter(pk=user.pk).update(date_joined=privacy.months_before(timezone.now(), 13))
    plan = privacy.account_operation(op, user.pk, "notice")
    privacy.account_operation(op, user.pk, "notice", plan["plan_hash"], review_confirmed=True)
    with patch("muqola.notifications.services.EmailMessage.send", side_effect=OSError):
        assert send_due() == 1
    assert not InactivityNotice.objects.exists()
    with pytest.raises(ValidationError):
        privacy.account_operation(op, user.pk, "account")


def test_new_login_discards_unsent_inactivity_notice() -> None:
    from muqola.notifications.services import send_due

    op, user = catalogue_operator(), member()
    User.objects.filter(pk=user.pk).update(date_joined=privacy.months_before(timezone.now(), 13))
    plan = privacy.account_operation(op, user.pk, "notice")
    privacy.account_operation(op, user.pk, "notice", plan["plan_hash"], review_confirmed=True)
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())
    with patch("muqola.notifications.services.EmailMessage.send") as mail:
        send_due()
    mail.assert_not_called()
    assert not InactivityNotice.objects.exists()


def test_restore_replay_is_signed_scoped_and_never_forces_active_loans() -> None:
    alice, bob, _, _, copy = scenario()
    op = catalogue_operator()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    # Simulates a post-backup receipt available from an independent current export.
    PrivacyReceipt.objects.create(subject_id=bob.pk, action="erase", created_at=timezone.now())
    signed = privacy.export_receipts(op)
    backup_at = timezone.now() - timedelta(days=2)
    with pytest.raises(ValidationError):
        privacy.replay_operation(op, signed + "tampered", backup_at)
    with override_settings(APP_BASE_URL="https://other.example.test"):
        with pytest.raises(ValidationError):
            privacy.replay_operation(op, signed, backup_at)
    with pytest.raises(ValidationError):
        privacy.replay_operation(op, signed, privacy.months_before(timezone.now(), 7))
    plan = privacy.replay_operation(op, signed, backup_at)
    result = privacy.replay_operation(
        op, signed, backup_at, plan["plan_hash"], review_confirmed=True
    )
    assert not result["reopening_allowed"] and result["loans_to_reconcile"] == [bob.pk]
    loan.refresh_from_db()
    bob.refresh_from_db()
    assert loan.state == Loan.State.ACCEPTED and bob.deletion_restricted_at is not None
    loans.transition(bob, loan.pk, "cancel")
    fresh = privacy.replay_operation(op, signed, backup_at)
    result = privacy.replay_operation(
        op, signed, backup_at, fresh["plan_hash"], review_confirmed=True
    )
    assert result["reopening_allowed"] and not User.objects.filter(pk=bob.pk).exists()


def test_production_guard_with_real_postgres_runtime_role() -> None:
    from psycopg import sql

    op, user = catalogue_operator(), member()
    request_deletion(user)
    plan = privacy.account_operation(op, user.pk, "account")
    role_name = "privacy_synthetic_runtime"
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role_name)))
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name))
        )
        cursor.execute(
            sql.SQL("GRANT SELECT, UPDATE ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role_name)))
    try:
        with override_settings(APP_ENV="production"), pytest.raises(PermissionDenied):
            privacy.account_operation(
                op, user.pk, "account", plan["plan_hash"], review_confirmed=True
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
    assert User.objects.filter(pk=user.pk).exists()


def test_cli_ledger_is_exclusive_private_and_never_printed(tmp_path: Path) -> None:
    op = catalogue_operator()
    path = tmp_path / "ledger.json"
    output = StringIO()
    call_command("privacy", "receipts", operator_id=op.pk, ledger_file=path, stdout=output)
    assert path.stat().st_mode & 0o077 == 0
    assert "signed_ledger" in json.loads(path.read_text())
    assert "signed_ledger" not in output.getvalue()
    with pytest.raises(CommandError):
        call_command("privacy", "receipts", operator_id=op.pk, ledger_file=path)


def test_password_reset_candidate_erased_between_lookup_and_lock() -> None:
    from muqola.identity.services import consume_token, issue_token

    user, op = member(), catalogue_operator()
    issue_token(user, AccountToken.Purpose.RESET)
    candidate = AccountToken.objects.get(user=user)
    request_deletion(user)
    apply_account(op, user)
    with patch("muqola.identity.services.usable_token", return_value=candidate):
        assert not consume_token(
            candidate.digest, AccountToken.Purpose.RESET, "Unused-password-123"
        )


def test_login_candidate_erased_during_authentication_returns_neutral_form(client: Client) -> None:
    user, op = member(), catalogue_operator()
    request_deletion(user)

    def authenticate(*args: Any, **kwargs: Any) -> User:
        apply_account(op, user)
        return user

    with patch("muqola.identity.views.authenticate", side_effect=authenticate):
        response = client.post(
            reverse("identity:login"), {"email": user.email, "password": "Unused-password-123"}
        )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "Adresse ou mot de passe incorrect" in response.content.decode()


def test_restore_replays_hold_before_any_scrubbing() -> None:
    alice, bob, _, _, copy = scenario()
    op = catalogue_operator()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7), "Synthetic dispute")
    loans.transition(alice, loan.pk, "decline")
    PrivacyHold.objects.create(loan=loan, until=timezone.now() + timedelta(days=3), code="dispute")
    PrivacyReceipt.objects.create(subject_id=alice.pk, action="restrict", created_at=timezone.now())
    signed = privacy.export_receipts(op)
    PrivacyHold.objects.all().delete()  # Represents the older isolated restore, not production.
    when = timezone.now() - timedelta(days=2)
    plan = privacy.replay_operation(op, signed, when)
    result = privacy.replay_operation(op, signed, when, plan["plan_hash"], review_confirmed=True)
    assert not result["reopening_allowed"]
    assert PrivacyHold.objects.filter(loan=loan).exists()
    copy.refresh_from_db()
    loan.refresh_from_db()
    assert copy.notes == "Notes" and loan.message == "Synthetic dispute"
    assert User.objects.filter(pk=alice.pk).exists()


def test_preexisting_security_disable_is_never_reactivated_for_erasure() -> None:
    alice, bob, _, _, copy = scenario()
    op = catalogue_operator()
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    request_deletion(alice)
    User.objects.filter(pk=alice.pk).update(is_active=False)
    apply_account(op, alice)
    alice.refresh_from_db()
    assert not alice.is_active
    loans.resolve(op, loan.pk, Loan.State.CANCELLED, "Synthetic resolution before handover")
    apply_account(op, alice)
    assert not User.objects.filter(pk=alice.pk).exists()


def test_restore_replay_refuses_the_production_primary_database() -> None:
    op = catalogue_operator()
    signed = privacy.export_receipts(op)
    from django.conf import settings

    with (
        override_settings(APP_ENV="production"),
        patch.dict(settings.DATABASES["default"], NAME="muqola"),
    ):
        with pytest.raises(ValidationError, match="isolée"):
            privacy.replay_operation(op, signed, timezone.now() - timedelta(days=1))
