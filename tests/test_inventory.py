from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import Client
from django.urls import reverse

from muqola.catalogue.models import Game, GameReport
from muqola.catalogue.services import report, search, write_game
from muqola.communities import services as communities
from muqola.communities.models import Membership
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import visible, write_copy
from tests.helpers import member

pytestmark = pytest.mark.django_db


def test_internal_catalogue_reuse_multiple_private_copies_and_no_leak(client: Client) -> None:
    alice, bob = member(), member("Bob")
    game = write_game(alice, {"title": "  Câtan   Édition "})
    first = write_copy(alice, game.pk, "Détail strictement privé", [])
    second = write_copy(alice, game.pk, "Deuxième exemplaire", [])
    assert first.pk != second.pk
    assert search(bob, "CATAN edition").get() == game
    assert visible(bob).count() == 0 and visible(alice).count() == 2
    client.force_login(bob)
    page = client.get(reverse("catalogue:detail", args=[game.pk])).content.decode()
    assert "Détail strictement privé" not in page and "alice@example.test" not in page
    assert "Alice" not in page
    assert client.get(reverse("inventory:detail", args=[first.pk])).status_code == 404
    assert client.get(reverse("inventory:detail", args=[uuid4()])).status_code == 404
    own = write_copy(bob, game.pk, "À moi", [])
    assert own.game_id == first.game_id
    assert Game.objects.count() == 1


def test_visibility_union_deduplication_and_withdrawal() -> None:
    alice, bob, clara = member(), member("Bob"), member("Clara")
    a, b = communities.create(alice, "A"), communities.create(alice, "B")
    Membership.objects.create(community=a, user=bob)
    Membership.objects.create(community=b, user=bob)
    game = write_game(alice, {"title": "Jeu"})
    item = write_copy(alice, game.pk, "", [a.pk, b.pk])
    assert list(visible(bob)) == [item]
    assert visible(clara).count() == 0
    write_copy(alice, game.pk, "", [a.pk, b.pk], withdrawn=True, copy_id=item.pk)
    assert visible(bob).count() == 0
    assert visible(alice).get().available is False


def test_only_owner_can_edit_and_only_own_communities_can_be_shared(client: Client) -> None:
    alice, bob = member(), member("Bob")
    a = communities.create(alice, "A")
    game = write_game(alice, {"title": "Jeu"})
    item = write_copy(alice, game.pk, "Secret", [])
    with pytest.raises(ValidationError):
        write_copy(bob, game.pk, "Tentative", [a.pk])
    assert OwnedGame.objects.count() == 1
    with pytest.raises(Http404):
        write_copy(bob, game.pk, "Tentative", [], copy_id=item.pk)
    client.force_login(bob)
    assert (
        client.post(reverse("inventory:edit", args=[item.pk]), {"notes": "intrusion"}).status_code
        == 404
    )
    item.refresh_from_db()
    assert item.notes == "Secret" and item.visibilities.count() == 0


def test_member_removal_revokes_access_and_owner_departure_removes_visibility() -> None:
    alice, bob = member(), member("Bob")
    a, b = communities.create(alice, "A"), communities.create(alice, "B")
    Membership.objects.create(community=a, user=bob)
    Membership.objects.create(community=b, user=bob)
    game = write_game(alice, {"title": "Jeu"})
    item = write_copy(alice, game.pk, "", [a.pk, b.pk])
    communities.remove(alice, a.pk, bob.pk)
    assert visible(bob).get() == item  # Accès conservé par B.
    communities.transfer(alice, b.pk, bob.pk)
    communities.remove(alice, b.pk, alice.pk)
    assert not GameVisibility.objects.filter(owned_game=item, community=b).exists()
    assert visible(bob).count() == 0
    assert visible(alice).get() == item


def test_reused_game_cannot_be_rewritten_even_after_other_copy_is_archived() -> None:
    alice, bob = member(), member("Bob")
    game = write_game(alice, {"title": "Original"})
    write_game(alice, {"title": "Corrigé"}, game.pk)
    copy = write_copy(bob, game.pk, "", [])
    copy.archived = True
    copy.save()
    with pytest.raises(ValidationError):
        write_game(alice, {"title": "Écrasé"}, game.pk)
    with pytest.raises(Http404):
        write_game(bob, {"title": "Écrasé"}, game.pk)
    game.refresh_from_db()
    assert game.title == "Corrigé" and game.ever_reused
    report(bob, game.pk, "Titre à corriger")
    report(bob, game.pk, "Précision")
    assert GameReport.objects.get().reason == "Précision"


def test_catalogue_validation_and_database_constraints() -> None:
    alice = member()
    with pytest.raises(ValidationError):
        write_game(alice, {"title": "Jeu", "players_min": 4, "players_max": 2})
    game = write_game(alice, {"title": "Même titre"})
    write_game(alice, {"title": "Même titre"})
    assert Game.objects.count() == 2
    with pytest.raises(IntegrityError), transaction.atomic():
        Game.objects.filter(pk=game.pk).update(players_min=4, players_max=2)
    copy = write_copy(alice, game.pk, "", [])
    community = communities.create(alice, "A")
    GameVisibility.objects.create(owned_game=copy, community=community)
    with pytest.raises(IntegrityError), transaction.atomic():
        GameVisibility.objects.create(owned_game=copy, community=community)


def test_search_filters_and_errors_do_not_disclose_foreign_copies(client: Client) -> None:
    alice, bob = member(), member("Bob")
    a = communities.create(alice, "A")
    game = write_game(alice, {"title": "Privé", "players_min": 2, "players_max": 4})
    write_copy(alice, game.pk, "", [a.pk])
    client.force_login(bob)
    assert "Privé" not in client.get(reverse("inventory:index")).content.decode()
    response = client.get(reverse("inventory:index"), {"community": str(a.pk)})
    assert response.status_code == 400 and "Privé" not in response.content.decode()
    with pytest.raises(PermissionDenied):
        search(member("Nonverifie", verified=False))


def test_generic_html_and_copy_notes_are_escaped(client: Client) -> None:
    alice = member()
    game = write_game(alice, {"title": "<script>alert(1)</script>"})
    item = write_copy(alice, game.pk, "<img src=x onerror=alert(1)>", [])
    client.force_login(alice)
    response = client.get(reverse("inventory:detail", args=[item.pk]))
    assert b"<script>" not in response.content and b"&lt;script&gt;" in response.content
    assert b"<img src=x" not in response.content
