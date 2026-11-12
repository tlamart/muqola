from datetime import timedelta
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
from muqola.inventory.services import archive, available, visible, write_copy
from muqola.loans import services as loans
from muqola.operations.services import moderate_game
from tests.helpers import member
from tests.test_loans import scenario

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


def hide_game(item: OwnedGame) -> None:
    operator = member("Operateur")
    operator.is_superuser = True
    operator.save(update_fields=["is_superuser"])
    moderate_game(operator, item.game_id, "Fiche abusive")


def test_hidden_copy_notes_can_change_without_restoring_visibility_or_lending() -> None:
    alice, bob, clara, community, item = scenario()
    other = communities.create(alice, "Autre")
    Membership.objects.create(community=other, user=clara)
    loan = loans.request_loan(bob, item.pk, loans.today() + timedelta(days=7))
    hide_game(item)

    saved = write_copy(
        alice,
        item.game_id,
        "  Notes après modération  ",
        [community.pk, other.pk],
        withdrawn=False,
        copy_id=item.pk,
    )
    item.refresh_from_db()
    item.game.refresh_from_db()
    assert saved.pk == item.pk and item.notes == "Notes après modération"
    assert item.game.hidden and item.withdrawn and not item.available
    assert visible(alice).get() == item
    assert not available(visible(alice)).exists()
    for user in (bob, clara):
        assert not visible(user).exists() and not search(user).exists()
        with pytest.raises(Http404):
            loans.request_loan(user, item.pk, loans.today() + timedelta(days=7))
    loan.refresh_from_db()
    assert loan.state == "CANCELLED"
    with pytest.raises(ValidationError):
        loans.transition(alice, loan.pk, "accept")
    assert item.loans.count() == 1


@pytest.mark.parametrize("hidden", [False, True])
def test_copy_edit_form_saves_notes_and_respects_moderation(client: Client, hidden: bool) -> None:
    alice, bob, clara, community, item = scenario()
    write_game(alice, {"title": "Exemplaire de régression MUQ-04"}, item.game_id)
    if hidden:
        hide_game(item)
    client.force_login(alice)
    url = reverse("inventory:edit", args=[item.pk])
    assert client.get(url).status_code == 200
    response = client.post(url, {"notes": "Notes corrigées", "communities": [str(community.pk)]})
    assert response.status_code == 302
    assert response["Location"] == reverse("inventory:detail", args=[item.pk])
    assert "Notes corrigées" in client.get(response["Location"]).content.decode()
    item.refresh_from_db()
    item.game.refresh_from_db()
    assert item.notes == "Notes corrigées" and item.game.hidden == hidden
    assert item.withdrawn == hidden and item.available == (not hidden)
    assert item.visibilities.get().community_id == community.pk

    if hidden:
        for user in (bob, clara):
            client.force_login(user)
            for name, pk in (("catalogue:detail", item.game_id), ("inventory:detail", item.pk)):
                assert client.get(reverse(name, args=[pk])).status_code == 404
            for name in ("catalogue:index", "inventory:index", "inventory:mine"):
                assert item.game.title not in client.get(reverse(name)).content.decode()
            request_url = reverse("inventory:request", args=[item.pk])
            assert client.get(request_url).status_code == 404
            assert (
                client.post(
                    request_url, {"due_date": loans.today() + timedelta(days=7)}
                ).status_code
                == 404
            )
        assert not item.loans.exists()


def test_hidden_game_rejects_new_copies_in_service_and_form(client: Client) -> None:
    alice, bob, _, _, item = scenario()
    hide_game(item)
    count = OwnedGame.objects.count()
    for user in (alice, bob):
        with pytest.raises(Http404):
            write_copy(user, item.game_id, "Nouvel exemplaire", [])
        client.force_login(user)
        url = reverse("catalogue:add-copy", args=[item.game_id])
        assert client.get(url).status_code == 404
        assert client.post(url, {"notes": "Nouvel exemplaire"}).status_code == 404
    assert OwnedGame.objects.count() == count


def test_hidden_copy_edit_remains_owner_only(client: Client) -> None:
    _, bob, clara, _, item = scenario()
    hide_game(item)
    for user in (bob, clara):
        with pytest.raises(Http404):
            write_copy(user, item.game_id, "Intrusion", [], copy_id=item.pk)
        client.force_login(user)
        url = reverse("inventory:edit", args=[item.pk])
        assert client.get(url).status_code == 404
        assert client.post(url, {"notes": "Intrusion"}).status_code == 404
    item.refresh_from_db()
    assert item.notes == "Notes" and item.owner.display_name == "Alice"


@pytest.mark.parametrize("hidden", [False, True])
def test_archived_copy_cannot_be_edited_even_if_game_is_hidden(
    client: Client, hidden: bool
) -> None:
    alice, _, _, _, item = scenario()
    if hidden:
        hide_game(item)
    archive(alice, item.pk)
    with pytest.raises(Http404):
        write_copy(alice, item.game_id, "Tentative", [], copy_id=item.pk)
    client.force_login(alice)
    url = reverse("inventory:edit", args=[item.pk])
    assert client.get(url).status_code == 404
    assert client.post(url, {"notes": "Tentative"}).status_code == 404
    item.refresh_from_db()
    assert item.archived and item.notes == "Notes" and not item.visibilities.exists()


@pytest.mark.parametrize("hidden", [False, True])
def test_copy_edit_cannot_replace_its_game_or_share_to_foreign_community(hidden: bool) -> None:
    alice, bob, _, community, item = scenario()
    if hidden:
        hide_game(item)
    other_game = write_game(alice, {"title": "Autre fiche"})
    with pytest.raises(ValidationError, match="ne peut pas être remplacée"):
        write_copy(alice, other_game.pk, "Tentative", [], copy_id=item.pk)
    foreign = communities.create(bob, "Étrangère")
    with pytest.raises(ValidationError, match="vos communautés actuelles"):
        write_copy(alice, item.game_id, "Tentative", [foreign.pk], copy_id=item.pk)
    item.refresh_from_db()
    assert item.notes == "Notes" and item.visibilities.get().community_id == community.pk


def test_hidden_copy_edit_preserves_accepted_loan_and_its_completion() -> None:
    alice, bob, _, _, item = scenario()
    loan = loans.request_loan(bob, item.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    hide_game(item)
    write_copy(alice, item.game_id, "Notes privées", [], copy_id=item.pk)
    loan.refresh_from_db()
    assert loan.state == "ACCEPTED"
    assert loans.contacts(bob, loan.pk) == {"owner": alice.email, "borrower": bob.email}
    loans.transition(alice, loan.pk, "handover")
    loans.transition(alice, loan.pk, "return")
    assert loans.contacts(bob, loan.pk) is None
