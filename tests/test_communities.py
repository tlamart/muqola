from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections
from django.http import Http404
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from muqola.communities import services
from muqola.communities.models import CommunityInvite, Membership, PendingJoin
from muqola.core.secrets import secret_cipher
from muqola.identity.models import User
from tests.helpers import member

pytestmark = pytest.mark.django_db


def raw(item: CommunityInvite) -> str:
    return secret_cipher("community-invite").decrypt(item.encrypted_token.encode()).decode()


def test_create_multiuse_invite_join_explicit_and_unique(client: Client) -> None:
    alice, bob, clara = member(), member("Bob"), member("Clara")
    community = services.create(alice, "Voisins", "Privée")
    invitation = services.invite(alice, community.pk)
    token = raw(invitation)
    assert token != invitation.digest and token not in invitation.encrypted_token
    assert (
        timedelta(days=6, hours=23)
        < invitation.expires_at - invitation.created_at
        < timedelta(days=7, seconds=1)
    )
    client.force_login(bob)
    response = client.get(reverse("communities:receive-invite", args=[token]), follow=True)
    assert response.status_code == 200
    assert not Membership.objects.filter(user=bob).exists()
    assert "Rejoindre Voisins" in response.content.decode()
    client.post(reverse("communities:join"))
    assert Membership.objects.filter(user=bob, community=community, active=True).count() == 1
    services.join(bob, invitation.digest)
    services.join(clara, invitation.digest)
    assert Membership.objects.filter(community=community, active=True).count() == 3


def test_foreign_community_and_admin_actions_are_hidden(client: Client) -> None:
    alice, bob, clara = member(), member("Bob"), member("Clara")
    community = services.create(alice, "Secret A")
    invitation = services.invite(alice, community.pk)
    other = services.create(clara, "Secret B")
    client.force_login(bob)
    assert client.get(reverse("communities:detail", args=[community.pk])).status_code == 404
    assert client.get(reverse("communities:detail", args=[uuid4()])).status_code == 404
    assert "Secret A" not in client.get(reverse("communities:index")).content.decode()
    services.join(bob, invitation.digest)
    assert client.get(reverse("communities:detail", args=[community.pk])).status_code == 200
    assert (
        "alice@example.test"
        not in client.get(reverse("communities:detail", args=[community.pk])).content.decode()
    )
    for operation in (
        lambda: services.invite(bob, community.pk),
        lambda: services.revoke(bob, community.pk, invitation.pk),
        lambda: services.remove(bob, community.pk, alice.pk),
        lambda: services.transfer(bob, community.pk, alice.pk),
        lambda: services.revoke(alice, other.pk, invitation.pk),
    ):
        with pytest.raises(Http404):
            operation()


def test_expired_or_revoked_invites_are_checked_at_confirmation(client: Client) -> None:
    alice, bob = member(), member("Bob")
    community = services.create(alice, "Amis")
    invitation = services.invite(alice, community.pk)
    client.force_login(bob)
    client.get(reverse("communities:receive-invite", args=[raw(invitation)]))
    services.revoke(alice, community.pk, invitation.pk)
    assert client.post(reverse("communities:join")).status_code == 400
    second = services.invite(alice, community.pk)
    CommunityInvite.objects.filter(pk=second.pk).update(
        created_at=timezone.now() - timedelta(days=3), expires_at=timezone.now() - timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        services.join(bob, second.digest)
    assert not Membership.objects.filter(user=bob).exists()


def test_last_admin_transfer_departure_and_rejoin() -> None:
    alice, bob = member(), member("Bob")
    community = services.create(alice, "Amis")
    invitation = services.invite(alice, community.pk)
    with pytest.raises(ValidationError):
        services.remove(alice, community.pk, alice.pk)
    services.join(bob, invitation.digest)
    services.transfer(alice, community.pk, bob.pk)
    services.remove(alice, community.pk, alice.pk)
    with pytest.raises(Http404):
        services.membership(alice, community.pk)
    services.join(alice, invitation.digest)
    assert services.membership(alice, community.pk).role == "member"
    assert services.membership(bob, community.pk).role == "admin"


def test_unverified_member_cannot_read_invitation_name_or_join(client: Client) -> None:
    alice, bob = member(), member("Bob", verified=False)
    community = services.create(alice, "Nom privé")
    invitation = services.invite(alice, community.pk)
    client.force_login(bob)
    response = client.get(
        reverse("communities:receive-invite", args=[raw(invitation)]), follow=True
    )
    assert "Nom privé" not in response.content.decode()
    assert client.post(reverse("communities:join")).status_code == 403
    with pytest.raises(PermissionDenied):
        services.join(bob, invitation.digest)


def test_invitation_survives_signup_verification_and_new_browser_login(client: Client) -> None:
    alice = member()
    community = services.create(alice, "Amis")
    invitation = services.invite(alice, community.pk)
    client.get(reverse("communities:receive-invite", args=[raw(invitation)]))
    password = "Fictif-Parcours-9847!"
    client.post(
        reverse("identity:signup"),
        {
            "email": "bob@example.test",
            "display_name": "Bob",
            "password": password,
            "password_confirm": password,
        },
    )
    bob = User.objects.get(email="bob@example.test")
    assert PendingJoin.objects.get(user=bob).digest == invitation.digest
    # La vérification des comptes est testée avec son vrai jeton dans les tests du lot 1.
    bob.email_verified_at = timezone.now()
    bob.save()
    fresh = Client()
    response = fresh.post(reverse("identity:login"), {"email": bob.email, "password": password})
    assert response["Location"] == reverse("communities:join")
    assert not Membership.objects.filter(user=bob).exists()
    assert fresh.post(reverse("communities:join")).status_code == 302
    assert not PendingJoin.objects.filter(user=bob).exists()


def test_get_requests_do_not_change_membership_or_revoke(client: Client) -> None:
    alice = member()
    community = services.create(alice, "Amis")
    invitation = services.invite(alice, community.pk)
    client.force_login(alice)
    assert (
        client.get(reverse("communities:remove", args=[community.pk, alice.pk])).status_code == 405
    )
    assert (
        client.get(reverse("communities:revoke", args=[community.pk, invitation.pk])).status_code
        == 405
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_admin_departures_keep_an_admin() -> None:
    alice, bob = member(), member("Bob")
    community = services.create(alice, "Amis")
    Membership.objects.create(user=bob, community=community, role="admin")
    barrier = Barrier(2)

    def leave(user: User) -> bool:
        try:
            barrier.wait(timeout=10)
            services.remove(user, community.pk, user.pk)
            return True
        except ValidationError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(leave, [alice, bob])) == 1
    assert Membership.objects.filter(community=community, active=True, role="admin").count() == 1
