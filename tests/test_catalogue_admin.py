"""HTTP security, domain decisions and OS-trusted operator provisioning."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import Client
from django.urls import reverse

from muqola.catalogue import moderation
from muqola.catalogue.models import Game, GameDecision
from muqola.catalogue.services import write_game
from muqola.communities.services import create
from muqola.identity.models import User
from muqola.operations.models import OperatorAction
from tests.helpers import catalogue_operator, member

pytestmark = pytest.mark.django_db


def web_operator() -> User:
    user = catalogue_operator()
    user.is_staff = True
    user.save()
    return user


def decision_payload(client: Client, game: Game, **changes: Any) -> dict[str, Any]:
    page = client.get(reverse("catalogue_admin:review", args=[game.pk]))
    data = {**page.context["form"].initial, "reason": "Revue synthétique", "kind": "standalone"}
    data["base_game_id"] = data["base_game_id"] or ""
    for key, value in data.items():
        if value is None:
            data[key] = ""
    return {**data, **changes}


@pytest.mark.parametrize(
    "role", ["ordinary", "community", "staff", "inactive", "unverified", "minor", "nonstaff"]
)
def test_admin_requires_all_operator_conditions(client: Client, role: str) -> None:
    user = member()
    game = write_game(user, {"title": "Proposition confidentielle"})
    if role == "community":
        create(user, "Privée")
    if role in ("inactive", "unverified", "minor", "nonstaff"):
        user.is_superuser = True
        user.is_staff = role != "nonstaff"
    if role == "staff":
        user.is_staff = True
    if role == "inactive":
        user.is_active = False
    if role == "unverified":
        user.email_verified_at = None
    if role == "minor":
        user.adult_confirmed_at = None
    user.save()
    client.force_login(user)
    for url in [
        reverse("catalogue_admin:index"),
        reverse("catalogue_admin:review", args=[game.pk]),
    ]:
        response = client.get(url, follow=True)
        assert response.status_code in (200, 403)
        assert game.title not in response.content.decode()
        assert client.post(url, {"status": "approved", "reason": "Bypass"}).status_code in (
            302,
            403,
            405,
        )
    assert not GameDecision.objects.exists()


def test_anonymous_no_admin_login_or_default_model_routes(client: Client) -> None:
    response = client.get(reverse("catalogue_admin:index"))
    assert response["Location"] == reverse("identity:login")
    user = web_operator()
    client.force_login(user)
    for path in [
        "/admin/",
        "/operator/auth/user/",
        "/operator/catalogue/game/add/",
    ]:
        assert client.get(path).status_code == 404
    assert client.post(reverse("catalogue_admin:index")).status_code == 405
    assert client.post(reverse("catalogue_admin:login")).status_code == 405


def test_review_queue_filters_search_pagination_and_xss(client: Client) -> None:
    owner = member()
    pending = write_game(
        owner, {"title": "<script>alert(1)</script>", "description": "<img src=x>"}
    )
    published = write_game(owner, {"title": "Approuvée"})
    op = web_operator()
    moderation.decide(op, published.pk, Game.Status.APPROVED, "Revue", {"kind": "standalone"})
    client.force_login(op)
    queue = client.get(reverse("catalogue_admin:index"))
    assert pending in queue.context["page"] and published not in queue.context["page"]
    assert "<script>alert(1)</script>" not in queue.content.decode()
    assert "&lt;script&gt;" in queue.content.decode()
    filtered = client.get(
        reverse("catalogue_admin:index"), {"status": "approved", "q": "Approuvée"}
    )
    assert list(filtered.context["page"]) == [published]
    for i in range(32):
        Game.objects.create(created_by=owner, title=f"Test {i}", title_key=f"test {i}")
    assert len(client.get(reverse("catalogue_admin:index")).context["page"]) == 30
    detail = client.get(reverse("catalogue_admin:review", args=[pending.pk]))
    assert "<img src=x>" not in detail.content.decode()
    assert owner.email not in detail.content.decode()


def test_csrf_revision_duplicates_and_domain_validation(client: Client) -> None:
    owner, op = member(), web_operator()
    game = write_game(owner, {"title": "Nouveau"})
    client.force_login(op)
    url = reverse("catalogue_admin:review", args=[game.pk])
    payload = decision_payload(client, game)
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(op)
    assert csrf.post(url, payload).status_code == 403
    cases: list[dict[str, Any]] = [
        {"kind": "unknown"},
        {"hidden": "False"},
        {"revision": "forged"},
        {"reason": ""},
        {"players_min": 8, "players_max": 2},
    ]
    for changes in cases:
        assert client.post(url, {**payload, **changes}).status_code == 400
        game.refresh_from_db()
        assert game.moderation_status == "pending"
        assert not GameDecision.objects.exists() and not OperatorAction.objects.exists()
    assert client.post(url, payload).status_code == 302
    assert client.post(url, payload).status_code == 400  # stale second tab
    game.refresh_from_db()
    assert game.moderation_status == "approved" and GameDecision.objects.count() == 1
    duplicate = write_game(owner, {"title": "Nouveau", "proposal_reason": "Homonymie à examiner"})
    duplicate_url = reverse("catalogue_admin:review", args=[duplicate.pk])
    duplicate_data = decision_payload(client, duplicate)
    assert client.post(duplicate_url, duplicate_data).status_code == 400
    assert (
        client.post(
            duplicate_url, {**duplicate_data, "homonym_reason": "Vraie homonymie synthétique"}
        ).status_code
        == 302
    )


def test_changes_rejection_history_and_audit_failure_rollback(client: Client) -> None:
    game = write_game(member(), {"title": "Revue"})
    client.force_login(web_operator())
    url = reverse("catalogue_admin:review", args=[game.pk])
    assert (
        client.post(
            url, decision_payload(client, game, status="pending", reason="Précisez")
        ).status_code
        == 302
    )
    assert (
        client.post(
            url, decision_payload(client, game, status="rejected", reason="Refus motivé")
        ).status_code
        == 302
    )
    assert GameDecision.objects.count() == OperatorAction.objects.count() == 2
    assert "Refus motivé" in client.get(url).content.decode()
    payload = decision_payload(client, game)
    with patch(
        "muqola.operations.services.OperatorAction.objects.create", side_effect=RuntimeError
    ):
        with pytest.raises(RuntimeError):
            client.post(url, payload)
    game.refresh_from_db()
    assert game.moderation_status == "rejected"
    assert GameDecision.objects.count() == 2


def promote(user: User, **options: Any) -> None:
    call_command(
        "promote_operator",
        email=user.email,
        confirm_email=user.email,
        reason="Habilitation synthétique revue",
        stdout=StringIO(),
        **options,
    )


def test_first_operator_and_subsequent_promotion_preserve_verification_and_password() -> None:
    first = member()
    first.set_password("Fictif-Synthetique-9847!")
    first.save()
    snapshot = (first.password, first.email_verified_at, first.adult_confirmed_at)
    promote(first, bootstrap=True)
    first.refresh_from_db()
    assert first.is_superuser and first.is_staff
    assert snapshot == (first.password, first.email_verified_at, first.adult_confirmed_at)
    assert OperatorAction.objects.get().action == "bootstrap_operator"
    second = member("Second")
    second.set_password("Fictif-Second-9847!")
    second.save()
    with pytest.raises(CommandError):
        promote(second, bootstrap=True)
    promote(second, operator=first.email)
    second.refresh_from_db()
    assert second.is_superuser and second.is_staff
    assert OperatorAction.objects.count() == 2
    with pytest.raises(CommandError):
        promote(second, operator=first.email)


@pytest.mark.parametrize(
    "state",
    ["inactive", "unverified", "adult_missing", "unusable", "bad_confirmation", "bad_reason"],
)
def test_promotion_fails_closed(state: str) -> None:
    user = member()
    user.set_password("Fictif-Synthetique-9847!")
    if state == "inactive":
        user.is_active = False
    if state == "unverified":
        user.email_verified_at = None
    if state == "adult_missing":
        user.adult_confirmed_at = None
    if state == "unusable":
        user.set_unusable_password()
    user.save()
    options = {
        "email": user.email,
        "confirm_email": user.email,
        "reason": "Motif",
        "bootstrap": True,
    }
    if state == "bad_confirmation":
        options["confirm_email"] = "other@example.test"
    if state == "bad_reason":
        options["reason"] = ""
    with pytest.raises(CommandError):
        call_command("promote_operator", stdout=StringIO(), **options)
    user.refresh_from_db()
    assert not user.is_superuser and not user.is_staff
    assert not OperatorAction.objects.exists()


def test_promotion_rollback_and_unauthorized_actor() -> None:
    target, outsider = member(), member("Outsider")
    target.set_password("Fictif-Synthetique-9847!")
    target.save()
    with pytest.raises(CommandError):
        promote(target, operator=outsider.email)
    with patch(
        "muqola.operations.services.OperatorAction.objects.create", side_effect=RuntimeError
    ):
        with pytest.raises(RuntimeError):
            promote(target, bootstrap=True)
    target.refresh_from_db()
    assert not target.is_staff and not target.is_superuser


@pytest.mark.django_db(transaction=True)
def test_two_first_operator_promotions_are_serialized() -> None:
    users = [member("First"), member("Second")]
    for user in users:
        user.set_password("Fictif-Synthetique-9847!")
        user.save()
    barrier = Barrier(2)

    def run(user: User) -> bool:
        try:
            barrier.wait(timeout=10)
            promote(user, bootstrap=True)
            return True
        except CommandError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(run, users)) == 1
    assert User.objects.filter(is_superuser=True).count() == OperatorAction.objects.count() == 1


@pytest.mark.parametrize("decision", ["approved", "pending", "rejected"])
def test_http_decision_preserves_existing_copies_shares_and_loans(
    client: Client, decision: str
) -> None:
    from datetime import timedelta

    from muqola.communities.models import Membership
    from muqola.inventory.models import GameVisibility, OwnedGame
    from muqola.inventory.services import write_copy
    from muqola.loans import services as loans
    from muqola.loans.models import Loan

    owner, borrower = member(), member("Borrower")
    community = create(owner, "Partage privé")
    Membership.objects.create(user=borrower, community=community)
    game = write_game(owner, {"title": "Fiche prêtée"})
    copies = [write_copy(owner, game.pk, f"Note {i}", [community.pk]) for i in range(3)]
    entries = [
        loans.request_loan(borrower, copy.pk, loans.today() + timedelta(days=7)) for copy in copies
    ]
    loans.transition(owner, entries[1].pk, "accept")
    loans.transition(owner, entries[2].pk, "accept")
    loans.transition(owner, entries[2].pk, "handover")
    snapshots = list(OwnedGame.objects.order_by("pk").values())
    shares = list(GameVisibility.objects.order_by("pk").values())
    client.force_login(web_operator())
    url = reverse("catalogue_admin:review", args=[game.pk])
    assert client.post(url, decision_payload(client, game, status=decision)).status_code == 302
    assert list(OwnedGame.objects.order_by("pk").values()) == snapshots
    assert list(GameVisibility.objects.order_by("pk").values()) == shares
    assert Loan.objects.count() == 3
    for i, loan in enumerate(entries):
        loan.refresh_from_db()
        expected = [
            "CANCELLED" if decision == "rejected" else "REQUESTED",
            "ACCEPTED",
            "HANDED_OVER",
        ][i]
        assert loan.state == expected and loan.owned_game_id == copies[i].pk
    loans.transition(owner, entries[1].pk, "handover")
    loans.transition(owner, entries[1].pk, "return")
    loans.transition(owner, entries[2].pk, "return")


def test_permissions_are_rechecked_and_rate_limit_has_no_decision_side_effect(
    client: Client,
) -> None:
    game = write_game(member(), {"title": "Concurrence droits"})
    op = web_operator()
    client.force_login(op)
    url = reverse("catalogue_admin:review", args=[game.pk])
    payload = decision_payload(client, game)
    with patch("muqola.operations.catalogue_admin.allowed", return_value=False):
        assert client.post(url, payload).status_code == 429
    User.objects.filter(pk=op.pk).update(is_superuser=False)
    assert client.post(url, payload).status_code == 302
    assert not GameDecision.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_web_reviews_cannot_overwrite_each_other() -> None:
    game = write_game(member(), {"title": "Deux onglets"})
    op = web_operator()
    first, second = Client(), Client()
    first.force_login(op)
    second.force_login(op)
    data = decision_payload(first, game)
    barrier = Barrier(2)

    def submit(client: Client) -> int:
        try:
            barrier.wait(timeout=10)
            return client.post(reverse("catalogue_admin:review", args=[game.pk]), data).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, [first, second])) == [302, 400]
    assert GameDecision.objects.count() == OperatorAction.objects.count() == 1


def test_approval_never_unhides_and_rejected_post_fields_are_escaped(client: Client) -> None:
    game = write_game(member(), {"title": "Masquée"})
    Game.objects.filter(pk=game.pk).update(hidden=True)
    client.force_login(web_operator())
    url = reverse("catalogue_admin:review", args=[game.pk])
    response = client.post(url, decision_payload(client, game, reason="<script>unsafe()</script>"))
    assert response.status_code == 302
    game.refresh_from_db()
    assert game.hidden and game.moderation_status == "approved"
    body = client.get(url).content.decode()
    assert "<script>unsafe()</script>" not in body and "&lt;script&gt;" in body
