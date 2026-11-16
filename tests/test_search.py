"""PostgreSQL ranking, aggregation and cross-scope privacy regressions."""

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from muqola.catalogue.matching import ranked
from muqola.catalogue.models import Game, GameAlias
from muqola.catalogue.moderation import decide, similar
from muqola.catalogue.services import search, write_game
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import borrowable, grouped
from muqola.loans.models import Loan
from tests.helpers import catalogue_operator, member

pytestmark = pytest.mark.django_db


def game(title: str, owner: User, **kwargs: Any) -> Game:
    return Game.objects.create(
        title=title,
        created_by=owner,
        moderation_status=Game.Status.APPROVED,
        kind=Game.Kind.STANDALONE,
        **kwargs,
    )


def test_ranking_accents_aliases_short_titles_typos_and_stable_ties() -> None:
    owner = member()
    exact = game("Régicide", owner)
    alias = game("Couronne", owner)
    GameAlias.objects.create(game=alias, title="RÉGICIDE")
    prefix = game("Régicide royal", owner)
    contains = game("Le régicide royal", owner)
    typo = game("Regicid", owner)
    GameAlias.objects.create(game=alias, title="Autre nom")
    GameAlias.objects.create(game=exact, title="Royalicide")
    result = list(search(owner, "  REGICIDE "))
    assert result == [exact, alias, prefix, contains, typo]
    assert {exact, alias} <= set(search(owner, "regicdie"))
    assert list(search(owner, "couronne"))[0] == alias
    short = game("Go", owner)
    short_prefix = game("Gobelins", owner)
    game("Algo", owner)
    assert list(search(owner, "go")) == [short, short_prefix]
    assert not search(owner, "g").exists()
    assert search(owner, "xyzzzzzz").count() == 0
    # Same normalized title is a legitimate reviewed homonym: UUID breaks ties.
    duplicate = game("RÉGICIDE", owner, id=UUID(int=1))
    assert list(search(owner, "regicide"))[:2] == [duplicate, exact]
    assert len(list(search(owner, "regicide"))) == 6


@pytest.mark.parametrize(
    "restriction",
    [
        "private",
        "foreign",
        "withdrawn",
        "archived",
        "hidden",
        "pending",
        "rejected",
        "merged",
        "owner_left",
        "reader_left",
        "inactive_owner",
        "unverified_owner",
        "own",
    ],
)
def test_borrow_scope_no_global_fallback_or_direct_access(client: Client, restriction: str) -> None:
    owner, reader = member(), member("Reader")
    a = Community.objects.create(name="A", created_by=owner)
    b = Community.objects.create(name="Secret B", created_by=owner)
    owner_membership = Membership.objects.create(user=owner, community=a)
    reader_membership = Membership.objects.create(user=reader, community=a)
    Membership.objects.create(user=owner, community=b)
    item_game = game("Jeu interdit", owner)
    item = OwnedGame.objects.create(game=item_game, owner=owner, notes="Notes privées")
    GameVisibility.objects.create(owned_game=item, community=b if restriction == "foreign" else a)
    if restriction == "private":
        item.visibilities.all().delete()
    elif restriction in {"withdrawn", "archived"}:
        setattr(item, restriction, True)
        item.save()
    elif restriction in {"hidden", "pending", "rejected", "merged"}:
        if restriction == "hidden":
            item_game.hidden = True
        elif restriction == "merged":
            item_game.merged_into = game("Cible", owner)
        else:
            item_game.moderation_status = restriction
        item_game.save()
    elif restriction == "owner_left":
        owner_membership.active = False
        owner_membership.save()
    elif restriction == "reader_left":
        reader_membership.active = False
        reader_membership.save()
    elif restriction == "inactive_owner":
        owner.is_active = False
        owner.save()
    elif restriction == "unverified_owner":
        owner.email_verified_at = None
        owner.save()
    elif restriction == "own":
        reader = owner
    client.force_login(reader)
    assert not borrowable(reader).exists()
    for mode in ("", "live-search"):
        response = client.get(
            reverse("inventory:index"), {"title": "Jeu"}, HTTP_X_REQUESTED_WITH=mode
        )
        assert response.status_code == 200
        assert response.context["games"].paginator.count == 0
        assert b"Jeu interdit" not in response.content
    assert client.get(reverse("inventory:game", args=[item_game.pk])).status_code == 404
    if restriction != "own":
        assert client.get(reverse("inventory:detail", args=[item.pk])).status_code == 404


def test_grouping_filters_counts_and_invisible_copy_invariance(client: Client) -> None:
    owner, reader, secret = member(), member("Reader"), member("Secret")
    a = Community.objects.create(name="Commune", created_by=owner)
    b = Community.objects.create(name="Autre commune", created_by=owner)
    for community in (a, b):
        for user in (owner, reader):
            Membership.objects.create(user=user, community=community)
    target = game("Jeu groupé", owner, players_min=2, players_max=4)
    items = [OwnedGame.objects.create(game=target, owner=owner) for _ in range(3)]
    for item in items:
        for community in (a, b):
            GameVisibility.objects.create(owned_game=item, community=community)
    Loan.objects.create(
        owned_game=items[0],
        owner=owner,
        borrower=reader,
        state="ACCEPTED",
        due_date=date(2099, 1, 1),
    )
    client.force_login(reader)
    url = reverse("inventory:index")
    params = {"title": "group", "community": str(a.pk), "players": "3"}
    before = client.get(url, params, HTTP_X_REQUESTED_WITH="live-search")
    found = before.context["games"][0]
    assert found.copy_count == 3 and found.available_count == 2
    assert before.context["games"].paginator.count == 1
    OwnedGame.objects.create(game=target, owner=secret, notes="invisible")
    secret_game = game("Jeu groupé secret", secret)
    OwnedGame.objects.create(game=secret_game, owner=secret)
    after = client.get(url, params, HTTP_X_REQUESTED_WITH="live-search")
    assert after.content == before.content
    assert secret.email.encode() not in after.content
    available = client.get(url, {**params, "only_available": "on"}).context["games"][0]
    assert available.copy_count == 2 and available.available_count == 2
    assert client.get(url, {**params, "players": "6"}).context["games"].paginator.count == 0
    detail = client.get(reverse("inventory:game", args=[target.pk]))
    assert len(detail.context["copies"]) == 3
    assert "Secret" not in detail.content.decode()


@pytest.mark.parametrize("endpoint", ["inventory:index", "catalogue:index"])
def test_fragments_same_selector_no_cache_and_verified_auth(client: Client, endpoint: str) -> None:
    owner = member()
    target = game("Sécurité", owner)
    assert client.get(reverse(endpoint), HTTP_X_REQUESTED_WITH="live-search").status_code == 302
    client.force_login(member("Unverified", verified=False))
    assert client.get(reverse(endpoint), HTTP_X_REQUESTED_WITH="live-search").status_code == 403
    client.force_login(owner)
    full = client.get(reverse(endpoint), {"title": "securite"})
    fragment = client.get(
        reverse(endpoint), {"title": "securite"}, HTTP_X_REQUESTED_WITH="live-search"
    )
    assert fragment.content in full.content
    assert b"<!doctype" not in fragment.content
    assert fragment["Cache-Control"] == "no-store"
    assert "connect-src 'self'" in fragment["Content-Security-Policy"]
    assert (str(target.pk).encode() in fragment.content) == (endpoint == "catalogue:index")


def test_operator_and_public_suggestions_share_engine_without_fuzzy_rejection() -> None:
    owner = member()
    target = game("Régicide", owner)
    proposal = write_game(owner, {"title": "Regicdie"})
    assert list(similar(proposal)) == list(search(owner, proposal.title)) == [target]
    # A fuzzy match is a suggestion only. Exact aliases still require a reason.
    decide(
        catalogue_operator(),
        proposal.pk,
        Game.Status.APPROVED,
        "Homonyme revu",
        {"kind": "standalone"},
    )
    GameAlias.objects.create(game=target, title="Couronne")
    with pytest.raises(ValidationError):
        write_game(owner, {"title": "COURONNE"})


@pytest.mark.parametrize("volume", [1, 10, 30, 65])
def test_search_sql_budget_with_many_games_and_aliases(client: Client, volume: int) -> None:
    owner, reader = member(), member("Reader")
    a = Community.objects.create(name="A", created_by=owner)
    for user in (owner, reader):
        Membership.objects.create(user=user, community=a)
    for index in range(volume):
        target = game(f"Régicide {index:03}", owner)
        for alias in range(3):
            GameAlias.objects.create(game=target, title=f"Couronne {index:03} {alias}")
        item = OwnedGame.objects.create(game=target, owner=owner)
        GameVisibility.objects.create(owned_game=item, community=a)
    client.force_login(reader)
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("inventory:index"), {"title": "couronne"})
    assert response.status_code == 200
    assert len(captured) == 9
    assert response.context["games"].paginator.count == volume
    assert len(response.context["games"]) == min(volume, 30)
    assert len(list(grouped(borrowable(reader), "couronne"))) == volume
    assert len(list(ranked(Game.objects.all(), "couronne"))) == volume
    fragment = client.get(
        reverse("inventory:index"),
        {"title": "couronne", "page": "2"},
        HTTP_X_REQUESTED_WITH="live-search",
    )
    outsider = member("Outsider")
    private_game = game("Couronne secrète", outsider)
    OwnedGame.objects.create(game=private_game, owner=outsider)
    assert (
        client.get(
            reverse("inventory:index"),
            {"title": "couronne", "page": "2"},
            HTTP_X_REQUESTED_WITH="live-search",
        ).content
        == fragment.content
    )


@pytest.mark.parametrize("endpoint", ["inventory:index", "catalogue:index"])
def test_search_input_and_pagination_bounds(client: Client, endpoint: str) -> None:
    owner = member()
    game("Régicide", owner)
    client.force_login(owner)
    url = reverse(endpoint)
    for value in ("-1", "bad", "9" * 5000):
        response = client.get(url, {"page": value}, HTTP_X_REQUESTED_WITH="live-search")
        assert response.status_code == 200
        assert response.context["games"].number == 1
    response = client.get(url, {"title": "x" * 121}, HTTP_X_REQUESTED_WITH="live-search")
    assert response.status_code == (400 if endpoint == "inventory:index" else 200)
    assert response.context["games"].paginator.count == 0


def test_search_timeout_is_local_and_has_accessible_native_fallback(client: Client) -> None:
    from unittest.mock import patch

    from django.db.models import QuerySet

    def slow_search(*args: object) -> QuerySet[Game]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(6)")
        return Game.objects.none()

    client.force_login(member())
    with patch("muqola.catalogue.views.services.search", side_effect=slow_search):
        response = client.get(reverse("catalogue:index"))
    assert response.status_code == 503 and response["Retry-After"] == "1"
    assert "Réessayez" in response.content.decode()
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == "0"
