from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse

from muqola.catalogue.services import write_game
from muqola.communities import services as communities
from muqola.communities.models import Membership
from muqola.inventory.services import write_copy
from muqola.loans import services as loans
from tests.helpers import member
from tests.test_loans import scenario

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("state", ["anonymous", "unverified", "verified"])
def test_navigation_matches_verification_and_has_no_private_contact(
    client: Client, state: str
) -> None:
    if state != "anonymous":
        user = member(verified=state == "verified")
        client.force_login(user)
    response = client.get(
        reverse("identity:dashboard")
        if state == "verified"
        else reverse("identity:pending")
        if state == "unverified"
        else "/"
    )
    body = response.content.decode()
    assert 'aria-controls="site-navigation"' in body
    assert 'aria-expanded="false"' in body
    assert "alice@example.test" not in body
    for route in ("inventory:index", "inventory:mine", "loans:index", "communities:index"):
        assert (f'href="{reverse(route)}"' in body) == (state == "verified")
    if state == "unverified":
        assert "Vérifier mon e-mail" in body
    if state == "verified":
        assert body.count('aria-current="page"') == 1
    assert "font-src 'self'" in response["Content-Security-Policy"]


def test_dashboard_summaries_use_only_accessible_copies_memberships_and_loans(
    client: Client,
) -> None:
    alice, bob, clara, _, copy = scenario()
    hidden_community = communities.create(clara, "Cercle secret de Clara")
    hidden_game = write_game(clara, {"title": "Jeu inaccessible au tableau de bord"})
    hidden_copy = write_copy(clara, hidden_game.pk, "", [hidden_community.pk])
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    Membership.objects.create(user=alice, community=hidden_community)
    loans.request_loan(alice, hidden_copy.pk, loans.today() + timedelta(days=7))
    client.force_login(bob)
    response = client.get(reverse("identity:dashboard"))
    body = response.content.decode()
    assert "Cercle secret" not in body and hidden_game.title not in body
    assert len(response.context["current_loans"]) == 1
    assert response.context["attention_count"] == 0
    assert response.context["community_count"] == 1
    assert response.context["collection_count"] == 0
    assert response.context["loan_count"] == 1
    assert alice.email not in body and clara.email not in body
    client.force_login(alice)
    response = client.get(reverse("identity:dashboard"))
    assert response.context["attention_count"] == 1
    assert "Demande à examiner" in response.content.decode()


def test_game_detail_never_lists_other_shared_community_or_private_copy(client: Client) -> None:
    alice, bob, clara, community, copy = scenario()
    secret = communities.create(alice, "Partage invisible pour Bob")
    write_copy(alice, copy.game_id, "", [community.pk, secret.pk], copy_id=copy.pk)
    write_copy(clara, copy.game_id, "Exemplaire privé de Clara", [])
    client.force_login(bob)
    response = client.get(reverse("catalogue:detail", args=[copy.game_id]))
    body = response.content.decode()
    assert community.name in body and secret.name not in body
    assert "Exemplaire privé de Clara" not in body and "Clara" not in body
    assert len(response.context["copy_rows"]) == 1
    assert alice.email not in body
    assert reverse("inventory:request", args=[copy.pk]) in body


@pytest.mark.parametrize("state", ["owner", "available", "busy"])
def test_game_request_action_is_for_an_available_copy_owned_by_someone_else(
    client: Client, state: str
) -> None:
    alice, bob, _, _, copy = scenario()
    if state == "busy":
        loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
        loans.transition(alice, loan.pk, "accept")
    client.force_login(alice if state == "owner" else bob)
    body = client.get(reverse("catalogue:detail", args=[copy.game_id])).content.decode()
    assert (reverse("inventory:request", args=[copy.pk]) in body) == (state == "available")
    assert alice.email not in body and bob.email not in body


def test_explorer_count_reflects_filtered_authorized_results(client: Client) -> None:
    alice, bob, clara, community, _ = scenario()
    game = write_game(alice, {"title": "Second jeu"})
    write_copy(alice, game.pk, "", [community.pk])
    hidden = write_game(clara, {"title": "Second secret"})
    write_copy(clara, hidden.pk, "", [])
    client.force_login(bob)
    response = client.get(reverse("inventory:index"), {"title": "Second"})
    assert response.context["copies"].paginator.count == 1
    body = response.content.decode()
    assert "Second jeu" in body and "Second secret" not in body
    assert "1 exemplaire accessible" in body


def test_owner_can_still_open_copy_when_its_generic_game_is_hidden(client: Client) -> None:
    alice, _, _, _, copy = scenario()
    copy.game.hidden = True
    copy.game.save()
    client.force_login(alice)
    body = client.get(reverse("inventory:index")).content.decode()
    assert reverse("inventory:detail", args=[copy.pk]) in body
    assert reverse("catalogue:detail", args=[copy.game_id]) not in body
    assert client.get(reverse("inventory:detail", args=[copy.pk])).status_code == 200
