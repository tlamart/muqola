from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from muqola.catalogue.models import Game
from muqola.catalogue.services import write_game
from muqola.communities import services as communities
from muqola.communities.models import CommunityInvite, Membership, PendingJoin
from muqola.inventory.models import OwnedGame
from muqola.inventory.services import write_copy
from tests.helpers import approved_game, member

pytestmark = pytest.mark.django_db


def test_invited_login_offers_signup_in_main_without_disclosing_community(client: Client) -> None:
    owner = member()
    community = communities.create(owner, "Nom privé à ne pas exposer")
    communities.invite(owner, community.pk)
    _, link = communities.current_invitation(owner, community.pk)
    client.get(link)
    response = client.get(reverse("identity:login"))
    main = response.content.decode().split('<main id="contenu"', 1)[1].split("</main>", 1)[0]
    assert f'href="{reverse("identity:signup")}"' in main
    assert "Créer mon compte" in main
    assert community.name not in main


@pytest.mark.parametrize("expired", [False, True])
def test_cancel_join_clears_only_own_intention_without_revoking_invitation(
    client: Client, expired: bool
) -> None:
    owner, bob, clara = member(), member("Bob"), member("Clara")
    community = communities.create(owner, "Cercle synthétique")
    invitation = communities.invite(owner, community.pk)
    _, link = communities.current_invitation(owner, community.pk)
    client.force_login(bob)
    client.get(link)
    communities.remember(clara, invitation.digest)
    if expired:
        communities.revoke(owner, community.pk, invitation.pk)
    before = CommunityInvite.objects.values().get(pk=invitation.pk)
    response = client.post(reverse("communities:join"), {"action": "cancel"})
    assert response.status_code == 302
    assert response["Location"] == reverse("identity:dashboard")
    assert not PendingJoin.objects.filter(user=bob).exists()
    assert PendingJoin.objects.filter(user=clara).exists()
    assert "community_invite" not in client.session
    assert not Membership.objects.filter(user=bob).exists()
    assert CommunityInvite.objects.values().get(pk=invitation.pk) == before


def test_cancel_join_preserves_existing_membership_and_requires_csrf(client: Client) -> None:
    owner, bob = member(), member("Bob")
    community = communities.create(owner, "Cercle")
    invitation = communities.invite(owner, community.pk)
    communities.join(bob, invitation.digest)
    client.force_login(bob)
    session = client.session
    session["community_invite"] = invitation.digest
    session.save()
    communities.remember(bob, invitation.digest)
    assert client.get(reverse("communities:join"), {"action": "cancel"}).status_code == 200
    assert PendingJoin.objects.filter(user=bob).exists()
    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(bob)
    assert guarded.post(reverse("communities:join"), {"action": "cancel"}).status_code == 403
    assert PendingJoin.objects.filter(user=bob).exists()
    client.post(reverse("communities:join"), {"action": "cancel"})
    assert Membership.objects.get(user=bob, community=community).active


def test_copy_preview_and_cancel_do_not_create_game_or_copy(client: Client) -> None:
    owner = member()
    client.force_login(owner)
    url = reverse("catalogue:index") + "?manual=1"
    response = client.post(url, {"step": "copy", "title": "Proposition synthétique"})
    assert response.status_code == 200
    assert response.templates[0].name == "catalogue/copy.html"
    assert not Game.objects.exists() and not OwnedGame.objects.exists()
    assert client.get(reverse("inventory:mine")).status_code == 200
    assert not Game.objects.exists() and not OwnedGame.objects.exists()
    response = client.post(url, {"step": "save", "title": "Proposition synthétique"})
    assert response.status_code == 302
    assert OwnedGame.objects.get().game.moderation_status == Game.Status.PENDING


def test_copy_wizard_preserves_draft_across_choice_and_revalidates_sharing(client: Client) -> None:
    owner = member()
    community = communities.create(owner, "Mes proches")
    first = approved_game(owner, {"title": "Premier jeu synthétique"})
    second = approved_game(owner, {"title": "Second jeu synthétique"})
    client.force_login(owner)
    url = reverse("catalogue:index")
    payload = {
        "step": "copy",
        "game_id": str(first.pk),
        "notes": "Notes à conserver",
        "communities": [str(community.pk)],
    }
    assert client.post(url, payload).status_code == 200
    response = client.post(url, payload | {"step": "choose"})
    assert response.status_code == 200
    assert response.templates[0].name == "catalogue/index.html"
    assert response.context["form"]["notes"].value() == "Notes à conserver"
    assert response.context["form"]["communities"].value() == [str(community.pk)]
    assert not OwnedGame.objects.exists()
    payload["game_id"] = str(second.pk)
    assert client.post(url, payload).context["selected_game"] == second
    response = client.post(url, payload | {"step": "save"})
    assert response.status_code == 302
    copy = OwnedGame.objects.get()
    assert copy.game == second and copy.notes == "Notes à conserver"
    assert copy.visibilities.get().community == community


@pytest.mark.parametrize(
    "state", ["approved", "own_pending", "foreign_pending", "rejected", "hidden"]
)
def test_copy_preview_has_same_game_permissions_as_final_save(client: Client, state: str) -> None:
    owner, bob = member(), member("Bob")
    game = write_game(owner, {"title": "Proposition synthétique"})
    if state == "approved":
        game = approved_game(owner, {"title": "Jeu approuvé synthétique"})
    elif state == "rejected":
        game.moderation_status = Game.Status.REJECTED
        game.save()
    elif state == "hidden":
        game.hidden = True
        game.save()
    client.force_login(bob if state == "foreign_pending" else owner)
    payload = {"game_id": str(game.pk), "step": "copy"}
    expected = 200 if state in {"approved", "own_pending"} else 404
    assert client.post(reverse("catalogue:index"), payload).status_code == expected
    assert not OwnedGame.objects.exists()


def test_final_save_rechecks_hidden_game_and_foreign_community(client: Client) -> None:
    owner, bob = member(), member("Bob")
    game = approved_game(owner, {"title": "Jeu synthétique"})
    foreign = communities.create(bob, "Communauté étrangère")
    client.force_login(owner)
    url = reverse("catalogue:index")
    payload = {"game_id": str(game.pk), "step": "copy"}
    assert client.post(url, payload).status_code == 200
    response = client.post(url, payload | {"step": "save", "communities": [str(foreign.pk)]})
    assert response.status_code == 400 and not OwnedGame.objects.exists()
    game.hidden = True
    game.save()
    assert client.post(url, payload | {"step": "save"}).status_code == 404
    assert not OwnedGame.objects.exists()


def test_wizard_invalid_fields_and_files_cannot_create_or_hide_errors(client: Client) -> None:
    owner = member()
    client.force_login(owner)
    url = reverse("catalogue:index") + "?manual=1"
    response = client.post(url, {"step": "copy", "title": "Jeu", "notes": "x" * 501})
    assert response.status_code == 400
    assert response.templates[0].name == "catalogue/copy.html"
    assert response.context["form"].errors["notes"]
    response = client.post(
        url,
        {"step": "copy", "title": "Jeu", "image": SimpleUploadedFile("test.txt", b"synthetic")},
    )
    assert response.status_code == 400
    assert not Game.objects.exists() and not OwnedGame.objects.exists()


def test_copy_management_is_on_owner_only_page_and_keeps_archive_guard(client: Client) -> None:
    owner, bob = member(), member("Bob")
    game = approved_game(owner, {"title": "Jeu synthétique"})
    item = write_copy(owner, game.pk, "Notes réservées à la gestion", [])
    client.force_login(owner)
    response = client.get(reverse("inventory:detail", args=[item.pk]))
    assert "Notes réservées à la gestion" not in response.content.decode()
    assert reverse("inventory:edit", args=[item.pk]) in response.content.decode()
    response = client.get(reverse("inventory:edit", args=[item.pk]))
    assert "Notes réservées à la gestion" in response.content.decode()
    assert reverse("inventory:archive", args=[item.pk]) in response.content.decode()
    client.force_login(bob)
    assert client.get(reverse("inventory:edit", args=[item.pk])).status_code == 404
    assert client.get(reverse("inventory:edit", args=[uuid4()])).status_code == 404
