from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connections, transaction
from django.http import Http404
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from muqola.catalogue.services import write_game
from muqola.communities import services as communities
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from muqola.inventory.services import archive, visible, write_copy
from muqola.loans import services
from muqola.loans.models import Loan, LoanEvent
from tests.helpers import member

pytestmark = pytest.mark.django_db


def scenario() -> tuple[User, User, User, Community, OwnedGame]:
    alice, bob, clara = member(), member("Bob"), member("Clara")
    community = communities.create(alice, "Amis")
    Membership.objects.create(user=bob, community=community)
    Membership.objects.create(user=clara, community=community)
    game = write_game(alice, {"title": "Jeu"})
    copy = write_copy(alice, game.pk, "Notes", [community.pk])
    return alice, bob, clara, community, copy


def test_complete_cycle_permissions_and_temporary_email_sharing(client: Client) -> None:
    alice, bob, clara, _, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7), "Demande")
    assert copy.available and services.contacts(bob, loan.pk) is None
    client.force_login(bob)
    url = reverse("loans:detail", args=[loan.pk])
    assert b"alice@example.test" not in client.get(url).content
    with pytest.raises(PermissionDenied):
        services.transition(bob, loan.pk, "accept")
    services.transition(alice, loan.pk, "accept")
    assert not copy.available
    assert services.contacts(bob, loan.pk) == {"owner": alice.email, "borrower": bob.email}
    assert b"alice@example.test" in client.get(url).content
    with pytest.raises(Http404):
        services.contacts(clara, loan.pk)
    client.force_login(clara)
    assert client.get(url).status_code == 404
    with pytest.raises(PermissionDenied):
        services.transition(bob, loan.pk, "handover")
    services.transition(alice, loan.pk, "handover")
    with pytest.raises(ValidationError):
        services.transition(bob, loan.pk, "cancel")
    with pytest.raises(PermissionDenied):
        services.transition(bob, loan.pk, "return")
    services.transition(alice, loan.pk, "return")
    assert copy.available and services.contacts(bob, loan.pk) is None
    client.force_login(bob)
    assert b"alice@example.test" not in client.get(url).content
    assert LoanEvent.objects.filter(loan=loan).count() == 4


def test_required_future_date_uses_paris_and_is_rechecked_on_acceptance() -> None:
    alice, bob, _, _, copy = scenario()
    frozen = datetime(2026, 7, 9, 22, 30, tzinfo=UTC)  # Paris est déjà le 10.
    with patch("django.utils.timezone.now", return_value=frozen):
        assert services.today() == date(2026, 7, 10)
        with pytest.raises(ValidationError):
            services.request_loan(bob, copy.pk, date(2026, 7, 10))
        loan = services.request_loan(bob, copy.pk, date(2026, 7, 11))
    with patch("muqola.loans.services.today", return_value=date(2026, 7, 11)):
        with pytest.raises(ValidationError):
            services.transition(alice, loan.pk, "accept")
    with pytest.raises(IntegrityError), transaction.atomic():
        Loan.objects.filter(pk=loan.pk).update(due_date=None)


def test_duplicate_pending_self_borrow_and_unavailable_requests_are_refused() -> None:
    alice, bob, clara, _, copy = scenario()
    due = services.today() + timedelta(days=7)
    with pytest.raises(ValidationError):
        services.request_loan(alice, copy.pk, due)
    first = services.request_loan(bob, copy.pk, due)
    with pytest.raises(ValidationError):
        services.request_loan(bob, copy.pk, due)
    services.transition(alice, first.pk, "accept")
    with pytest.raises(ValidationError):
        services.request_loan(clara, copy.pk, due)
    with pytest.raises(ValidationError):
        archive(alice, copy.pk)


def test_acceptance_closes_other_requests_and_release_does_not_reopen_them() -> None:
    alice, bob, clara, _, copy = scenario()
    first = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    second = services.request_loan(clara, copy.pk, first.due_date)
    services.transition(alice, first.pk, "accept")
    second.refresh_from_db()
    assert second.state == "CANCELLED" and second.close_reason
    services.transition(bob, first.pk, "cancel")
    assert copy.available
    second.refresh_from_db()
    assert second.state == "CANCELLED"


@pytest.mark.parametrize("change", ["visibility", "withdraw", "borrower", "owner"])
def test_permission_changes_close_pending_requests(change: str) -> None:
    alice, bob, _, community, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    if change == "visibility":
        write_copy(alice, copy.game_id, "", [], copy_id=copy.pk)
    elif change == "withdraw":
        write_copy(alice, copy.game_id, "", [community.pk], withdrawn=True, copy_id=copy.pk)
    elif change == "borrower":
        communities.remove(alice, community.pk, bob.pk)
    else:
        communities.transfer(alice, community.pk, bob.pk)
        communities.remove(alice, community.pk, alice.pk)
    loan.refresh_from_db()
    assert loan.state == "CANCELLED" and loan.close_reason
    with pytest.raises(ValidationError):
        services.transition(alice, loan.pk, "accept")


def test_active_loan_stays_private_and_closable_after_membership_and_visibility_loss(
    client: Client,
) -> None:
    alice, bob, clara, community, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    services.transition(alice, loan.pk, "accept")
    communities.remove(alice, community.pk, bob.pk)
    write_copy(alice, copy.game_id, "", [], withdrawn=True, copy_id=copy.pk)
    assert not visible(bob).exists()
    client.force_login(bob)
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 200
    with pytest.raises(Http404):
        services.contacts(clara, loan.pk)
    services.transition(alice, loan.pk, "handover")
    services.transition(alice, loan.pk, "return")
    assert services.contacts(bob, loan.pk) is None


def test_alternative_common_community_keeps_pending_request_eligible() -> None:
    alice, bob, _, community, copy = scenario()
    other = communities.create(alice, "Autre")
    Membership.objects.create(user=bob, community=other)
    write_copy(alice, copy.game_id, "", [community.pk, other.pk], copy_id=copy.pk)
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    communities.remove(alice, community.pk, bob.pk)
    loan.refresh_from_db()
    assert loan.state == "REQUESTED"
    services.transition(alice, loan.pk, "accept")


def test_refusal_cancellation_and_admin_resolution_are_traced() -> None:
    alice, bob, _, _, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    services.transition(alice, loan.pk, "decline")
    assert services.contacts(bob, loan.pk) is None
    loan = services.request_loan(bob, copy.pk, loan.due_date)
    services.transition(alice, loan.pk, "accept")
    services.transition(alice, loan.pk, "handover")
    with pytest.raises(PermissionDenied):
        services.resolve(bob, loan.pk, "RETURNED", "Traitement")
    operator = member("Operateur")
    operator.is_superuser = True
    operator.save()
    services.resolve(operator, loan.pk, "RETURNED", "Retour confirmé par les parties")
    assert loan.events.filter(administrative=True, actor=operator).count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_acceptances_only_one_succeeds() -> None:
    alice, bob, clara, _, copy = scenario()
    first = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    second = services.request_loan(clara, copy.pk, first.due_date)
    barrier = Barrier(2)

    def accept(loan: Loan) -> bool:
        try:
            barrier.wait(timeout=10)
            services.transition(alice, loan.pk, "accept")
            return True
        except ValidationError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(accept, [first, second])) == 1
    assert Loan.objects.filter(owned_game=copy, state="ACCEPTED").count() == 1
    assert Loan.objects.filter(owned_game=copy, state="CANCELLED").count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_partial_unique_index_blocks_direct_concurrent_writes() -> None:
    _, bob, clara, _, copy = scenario()
    first = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    second = services.request_loan(clara, copy.pk, first.due_date)
    barrier = Barrier(2)

    def raw_accept(loan: Loan) -> bool:
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                Loan.objects.filter(pk=loan.pk).update(state="ACCEPTED", accepted_at=timezone.now())
            return True
        except IntegrityError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(raw_accept, [first, second])) == 1


def test_partial_pending_and_self_borrow_constraints_cannot_be_bypassed() -> None:
    alice, bob, _, _, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    with pytest.raises(IntegrityError), transaction.atomic():
        Loan.objects.create(owned_game=copy, owner=alice, borrower=bob, due_date=loan.due_date)
    with pytest.raises(IntegrityError), transaction.atomic():
        Loan.objects.create(owned_game=copy, owner=alice, borrower=alice, due_date=loan.due_date)


def test_overdue_accepted_loan_can_still_be_handed_over_and_returned() -> None:
    alice, bob, _, _, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=1))
    services.transition(alice, loan.pk, "accept")
    with patch("muqola.loans.services.today", return_value=loan.due_date + timedelta(days=2)):
        services.transition(alice, loan.pk, "handover")
        services.transition(alice, loan.pk, "return")
    loan.refresh_from_db()
    assert loan.state == "RETURNED"


def test_direct_http_actions_check_actor_and_method(client: Client) -> None:
    alice, bob, clara, _, copy = scenario()
    loan = services.request_loan(bob, copy.pk, services.today() + timedelta(days=7))
    client.force_login(clara)
    assert client.post(reverse("loans:action", args=[loan.pk, "accept"])).status_code == 404
    client.force_login(bob)
    assert client.post(reverse("loans:action", args=[loan.pk, "accept"])).status_code == 403
    assert client.get(reverse("loans:action", args=[loan.pk, "cancel"])).status_code == 405
    loan.refresh_from_db()
    assert loan.state == "REQUESTED"
