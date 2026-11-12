from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import Client
from django.urls import reverse

from muqola.catalogue.models import Game
from muqola.catalogue.services import write_game
from muqola.communities.services import create
from muqola.inventory.models import OwnedGame
from muqola.inventory.services import add_to_collection, visible
from tests.helpers import member

pytestmark = pytest.mark.django_db


def test_search_select_and_add_without_visiting_game_detail(client: Client) -> None:
    alice, bob = member(), member("Bob")
    game = write_game(alice, {"title": "Régicide synthétique", "year": 2020})
    private = add_to_collection(alice, game.pk, "", "Secret privé", [])
    client.force_login(bob)
    url = reverse("catalogue:index")
    response = client.get(url, {"title": "REGICIDE"})
    assert response.status_code == 200
    assert "Régicide synthétique" in response.content.decode()
    assert "2020" in response.content.decode()
    assert (
        "Secret privé" not in response.content.decode()
        and "alice@example.test" not in response.content.decode()
    )
    assert response.context["games"].paginator.count == 1
    response = client.post(url, {"game_id": str(game.pk), "notes": "Mon exemplaire"})
    assert response.status_code == 302
    owned = OwnedGame.objects.get(owner=bob)
    assert (
        owned.game == game and owned.notes == "Mon exemplaire" and not owned.visibilities.exists()
    )
    assert not visible(alice).filter(pk=owned.pk).exists()
    assert not visible(bob).filter(pk=private.pk).exists()
    assert Game.objects.count() == 1
    client.post(url, {"game_id": str(game.pk)})
    assert OwnedGame.objects.filter(owner=bob, game=game).count() == 2


def test_manual_creation_is_atomic_and_supports_multiple_communities(client: Client) -> None:
    alice, bob = member(), member("Bob")
    a, b, foreign = create(alice, "A"), create(alice, "B"), create(bob, "Autre")
    client.force_login(alice)
    url = reverse("catalogue:index") + "?manual=1&title=Inédit"
    assert client.get(url).status_code == 200
    response = client.post(url, {"title": "Inédit", "communities": [str(a.pk), str(b.pk)]})
    assert response.status_code == 302
    owned = OwnedGame.objects.get(owner=alice)
    assert owned.game.title == "Inédit" and owned.visibilities.count() == 2
    before = Game.objects.count()
    assert (
        client.post(
            url, {"title": "Orphelin interdit", "communities": [str(foreign.pk)]}
        ).status_code
        == 400
    )
    assert Game.objects.count() == before
    with pytest.raises(ValidationError):
        add_to_collection(alice, None, "Rollback service", "", [foreign.pk])
    assert Game.objects.count() == before
    with patch("muqola.inventory.services.write_copy", side_effect=RuntimeError("panne")):
        with pytest.raises(RuntimeError):
            add_to_collection(alice, None, "Panne atomique", "", [])
    assert Game.objects.count() == before


def test_manual_duplicate_needs_explicit_distinct_edition_confirmation(client: Client) -> None:
    alice = member()
    existing = write_game(alice, {"title": "Câtan"})
    client.force_login(alice)
    url = reverse("catalogue:index") + "?manual=1&title=CATAN"
    response = client.get(url)
    assert response.context["games"][0].pk == existing.pk
    assert existing.title in response.content.decode()
    assert client.post(url, {"title": "CATAN"}).status_code == 400
    assert not OwnedGame.objects.exists()
    with pytest.raises(ValidationError, match="existe déjà"):
        add_to_collection(alice, None, "CATAN", "", [])
    assert Game.objects.count() == 1
    item = add_to_collection(alice, None, "Catan", "", [], distinct_edition=True)
    assert item.game_id != existing.pk and Game.objects.count() == 2


def test_hidden_games_and_foreign_copy_ids_cannot_be_used(client: Client) -> None:
    alice, bob = member(), member("Bob")
    game = write_game(alice, {"title": "Masqué"})
    game.hidden = True
    game.save()
    client.force_login(bob)
    url = reverse("catalogue:index")
    assert "Masqué" not in client.get(url).content.decode()
    assert client.post(url, {"game_id": str(game.pk)}).status_code == 404
    assert not OwnedGame.objects.exists()
    game.hidden = False
    game.save()
    item = add_to_collection(alice, game.pk, "", "Alice", [])
    response = client.post(
        url, {"game_id": str(game.pk), "copy_id": str(item.pk), "owner": alice.pk, "notes": "Bob"}
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.notes == "Alice" and OwnedGame.objects.get(owner=bob).notes == "Bob"


@pytest.mark.parametrize(
    "payload", [{}, {"game_id": "bad"}, {"title": "x" * 121}, {"notes": "x" * 501}]
)
def test_invalid_input_does_not_create_anything(client: Client, payload: dict[str, str]) -> None:
    client.force_login(member())
    assert client.post(reverse("catalogue:index"), payload).status_code == 400
    assert not Game.objects.exists() and not OwnedGame.objects.exists()


def test_unverified_users_and_csrf_are_rejected(client: Client) -> None:
    alice = member(verified=False)
    client.force_login(alice)
    assert client.post(reverse("catalogue:index"), {"title": "Non"}).status_code == 403
    with pytest.raises(PermissionDenied):
        add_to_collection(alice, None, "Non", "", [])
    with pytest.raises(Http404):
        from uuid import uuid4

        add_to_collection(member("Bob"), uuid4(), "", "", [])
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(member("Clara"))
    assert csrf_client.post(reverse("catalogue:index"), {"title": "Sans CSRF"}).status_code == 403


def test_search_is_bounded_prioritizes_exact_title_and_has_no_per_game_queries(
    client: Client,
) -> None:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    alice = member()
    exact = write_game(alice, {"title": "Édition"})
    client.force_login(alice)
    url = reverse("catalogue:index")
    with CaptureQueriesContext(connection) as first_queries:
        first = client.get(url, {"title": "EDITION"})
    assert first.status_code == 200
    for i in range(24):
        write_game(alice, {"title": f"A édition {i}"})
    with CaptureQueriesContext(connection) as many_queries:
        response = client.get(url, {"title": "EDITION"})
    games = response.context["games"]
    assert games.paginator.count == 25 and len(games) == 10 and games[0].pk == exact.pk
    assert len(first_queries) == len(many_queries)
    assert len(client.get(url, {"title": "EDITION", "page": "3"}).context["games"]) == 5
