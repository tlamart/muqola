from datetime import date
from uuid import UUID

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from muqola.catalogue.models import Game
from muqola.communities.models import Community, Membership
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import available, visible, with_availability
from muqola.loans.models import Loan
from tests.helpers import member

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("volume", [1, 10, 30, 65])
@pytest.mark.parametrize("view", ["inventory:index", "inventory:mine", "catalogue:detail"])
def test_page_query_count(client: Client, volume: int, view: str) -> None:
    owner, reader = member(), member("Reader")
    community = Community.objects.create(name="Partagée", created_by=owner)
    Membership.objects.create(community=community, user=owner)
    Membership.objects.create(community=community, user=reader)
    game = Game.objects.create(title="Jeu SQL", created_by=owner)
    items = OwnedGame.objects.bulk_create(
        [OwnedGame(game=game, owner=owner) for _ in range(volume)]
    )
    GameVisibility.objects.bulk_create(
        [GameVisibility(owned_game=item, community=community) for item in items]
    )
    client.force_login(owner if view == "inventory:mine" else reader)
    url = reverse(view, args=[game.pk] if view == "catalogue:detail" else [])
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200
    print(f"SQL {view} volume={volume}: {len(captured)}")
    assert len(captured) == {"inventory:index": 6, "inventory:mine": 4, "catalogue:detail": 9}[view]
    assert len(response.context["copies"]) == min(volume, 30)


@pytest.mark.parametrize("state", [None, *Loan.State.values])
@pytest.mark.parametrize("restriction", [None, "withdrawn", "archived", "hidden"])
def test_annotated_availability_matches_fallback_and_filter(
    state: str | None,
    restriction: str | None,
) -> None:
    owner, borrower = member(), member("Borrower")
    game = Game.objects.create(title="États", created_by=owner, hidden=restriction == "hidden")
    item = OwnedGame.objects.create(
        game=game,
        owner=owner,
        withdrawn=restriction == "withdrawn",
        archived=restriction == "archived",
    )
    if state:
        Loan.objects.create(
            owned_game=item,
            owner=owner,
            borrower=borrower,
            state=state,
            due_date=date(2099, 1, 1),
        )
    expected = restriction is None and state not in {"ACCEPTED", "HANDED_OVER"}
    assert item.available is expected
    annotated = with_availability(OwnedGame.objects.select_related("game")).get(pk=item.pk)
    with CaptureQueriesContext(connection) as captured:
        assert annotated.available is expected
        assert annotated.available is expected
    assert len(captured) == 0
    assert available(OwnedGame.objects.all()).filter(pk=item.pk).exists() is expected


def test_detail_pagination_preserves_visibility_and_global_availability(client: Client) -> None:
    owner, reader, outsider = member(), member("Reader"), member("SecretOwner")
    a = Community.objects.create(name="Autorisée", created_by=owner)
    b = Community.objects.create(name="Communauté secrète", created_by=owner)
    Membership.objects.create(community=a, user=owner)
    membership = Membership.objects.create(community=a, user=reader)
    Membership.objects.create(community=b, user=owner)
    game = Game.objects.create(title="Pagination", created_by=owner)
    items = OwnedGame.objects.bulk_create(
        [OwnedGame(id=UUID(int=i + 1), game=game, owner=owner) for i in range(65)]
    )
    GameVisibility.objects.bulk_create(
        [
            GameVisibility(owned_game=item, community=community)
            for item in items
            for community in (a, b)
        ]
    )
    # Seul le dernier exemplaire est disponible : le badge global doit rester vrai.
    Loan.objects.bulk_create(
        [
            Loan(
                owned_game=item,
                owner=owner,
                borrower=reader,
                state="ACCEPTED",
                due_date=date(2099, 1, 1),
            )
            for item in items[:-1]
        ]
    )
    private = OwnedGame.objects.create(game=game, owner=outsider)
    foreign = OwnedGame.objects.create(game=game, owner=outsider)
    GameVisibility.objects.create(owned_game=foreign, community=b)
    client.force_login(reader)
    url = reverse("catalogue:detail", args=[game.pk])
    seen: list[UUID] = []
    counts = []
    for page in (1, 2, 3):
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url, {"page": page})
        counts.append(len(captured))
        copies = response.context["copies"]
        assert copies.paginator.count == 65
        assert len(copies) <= 30
        assert response.context["has_available"] is True
        seen.extend(item.pk for item in copies)
        body = response.content.decode()
        assert "Communauté secrète" not in body
        assert "SecretOwner" not in body
        assert "alice@example.test" not in body
        assert all(row["communities"] == ["Autorisée"] for row in response.context["copy_rows"])
    assert counts == [9, 9, 9]
    assert seen == [item.pk for item in items]
    assert private.pk not in seen and foreign.pk not in seen
    assert client.get(url, {"page": "invalide"}).context["copies"].number == 1
    assert client.get(url, {"page": 999}).context["copies"].number == 3
    assert (
        client.get(reverse("inventory:index"), {"only_available": "on"})
        .context["copies"]
        .paginator.count
        == 1
    )
    membership.active = False
    membership.save()
    response = client.get(url)
    assert response.context["copies"].paginator.count == 0
    assert response.context["has_available"] is False
    assert not visible(reader).exists()
    assert client.get(reverse("inventory:detail", args=[items[-1].pk])).status_code == 404


@pytest.mark.parametrize("volume", [1, 10, 30, 65])
def test_available_explorer_query_count(client: Client, volume: int) -> None:
    owner = member()
    game = Game.objects.create(title="Filtrés", created_by=owner)
    OwnedGame.objects.bulk_create([OwnedGame(game=game, owner=owner) for _ in range(volume)])
    client.force_login(owner)
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("inventory:index"), {"only_available": "on"})
    assert response.status_code == 200
    assert len(captured) == 6
    assert response.context["copies"].paginator.count == volume
    assert len(response.context["copies"]) == min(volume, 30)
