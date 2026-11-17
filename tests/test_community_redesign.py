"""Contrat C1/C2 : droits privés, liens compatibles et sérialisation réelle."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from muqola.communities import services
from muqola.communities.models import Community, CommunityInvite, InvitationEvent, Membership
from tests.helpers import member

pytestmark = pytest.mark.django_db


def test_creation_cards_counts_sql_and_fallback(client: Client) -> None:
    owner, other = member(), member("Other")
    client.force_login(owner)
    index = reverse("communities:index")
    assert "Créer une communauté" in client.get(index).content.decode()
    assert client.post(index, {"name": "Ancien chemin"}).status_code == 405
    assert (
        client.post(
            reverse("communities:create"), {"name": "Amis", "illustration": "https://bad.test/x"}
        ).status_code
        == 200
    )
    response = client.post(reverse("communities:create"), {"name": "Amis", "illustration": "dice"})
    assert response.status_code == 302
    community = Community.objects.get(name="Amis")
    Membership.objects.create(community=community, user=other)
    inactive = member("Inactive")
    inactive.is_active = False
    inactive.save()
    Membership.objects.create(community=community, user=inactive)
    unverified = member("Unverified", verified=False)
    Membership.objects.create(community=community, user=unverified)
    services.create(other, "Invisible")
    response = client.get(index)
    assert response.context["memberships"][0].member_count == 2
    body = response.content.decode()
    assert "Privée" in body and "communities/dice." in body and "Invisible" not in body
    assert "<form" not in body.split("<main")[1].split("</main>")[0]
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as before:
        client.get(index)
    for i in range(5):
        services.create(owner, f"Groupe {i}")
    with CaptureQueriesContext(connection) as after:
        client.get(index)
    assert len(before) == len(after)
    community.illustration = "unknown"
    assert community.illustration_path == "communities/table.svg"
    with pytest.raises(ValidationError):
        services.update(owner, community.pk, "Amis", "", "arbitrary")


def test_current_link_membership_mutations_csrf_and_get(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    owner, reader, outsider = member(), member("Reader"), member("Outsider")
    community = services.create(owner, "Secret")
    assert services.current_invitation(owner, community.pk) == (None, "")
    invitation = services.invite(owner, community.pk)
    services.join(reader, invitation.digest)
    client.force_login(reader)
    detail = reverse("communities:detail", args=[community.pk])
    response = client.get(detail)
    link = services.current_invitation(reader, community.pk)[1]
    assert link in response.content.decode() and "Lien permanent" in response.content.decode()
    assert response["Cache-Control"].find("no-store") >= 0
    assert response["Referrer-Policy"] == "same-origin"
    assert client.post(detail, {"action": "invite"}).status_code == 404
    revoke = reverse("communities:revoke", args=[community.pk, invitation.pk])
    assert client.post(revoke).status_code == 404
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(owner)
    assert csrf.post(detail, {"action": "invite"}).status_code == 403
    client.force_login(owner)
    count = CommunityInvite.objects.count()
    assert client.get(revoke).status_code == 405
    client.get(detail)
    assert CommunityInvite.objects.count() == count
    services.remove(reader, community.pk, reader.pk)
    for user in (reader, outsider):
        with patch("muqola.communities.services.secret_cipher") as cipher:
            with pytest.raises(Http404):
                services.current_invitation(user, community.pk)
            cipher.assert_not_called()
    assert invitation.digest not in caplog.text and link not in caplog.text
    event = InvitationEvent.objects.get()
    assert event.reason == "admin_request" and event.action == "rotate"


def test_optional_expiry_boundary_and_failed_rotation_rollback() -> None:
    owner = member()
    community = services.create(owner, "Amis")
    first = services.invite(owner, community.pk)
    with pytest.raises(ValidationError):
        services.invite(owner, community.pk, 0)
    with patch("muqola.communities.services.secrets.token_urlsafe", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            services.invite(owner, community.pk)
    assert services.valid_invite(first.digest)
    dated = services.invite(owner, community.pk, 3)
    assert dated.expires_at is not None and dated.expires_at > timezone.now()
    with patch("muqola.communities.services.timezone.now", return_value=dated.expires_at):
        assert services.valid_invite(dated.digest) is None
    with transaction.atomic(), pytest.raises(IntegrityError):
        CommunityInvite.objects.filter(pk=dated.pk).update(expires_at=dated.created_at)


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_historical_links_and_community() -> None:
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [(app, "0001_initial" if app == "communities" else name) for app, name in latest]
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        user = apps.get_model("identity", "User").objects.create(
            email="migration@example.test", password="!"
        )
        community = apps.get_model("communities", "Community").objects.create(
            name="Historique", created_by=user
        )
        Invite = apps.get_model("communities", "CommunityInvite")
        now = timezone.now()
        snapshots = []
        for i, days in enumerate([-1, 1, 3]):
            item = Invite.objects.create(
                community=community,
                created_by=user,
                digest=str(i) * 64,
                encrypted_token="historical",
                created_at=now - timedelta(days=4),
                expires_at=now + timedelta(days=days),
                revoked_at=now if i == 1 else None,
            )
            snapshots.append(
                (item.pk, item.expires_at, item.revoked_at, item.digest, item.encrypted_token)
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
    for pk, expires, revoked, digest, ciphertext in snapshots:
        item = CommunityInvite.objects.get(pk=pk)
        assert (item.expires_at, item.revoked_at, item.digest, item.encrypted_token) == (
            expires,
            revoked,
            digest,
            ciphertext,
        )
    assert Community.objects.get(pk=community.pk).illustration == "table"
    # Plusieurs liens historiques valides : aucun n'est modifié par consultation.
    owner = member()
    Membership.objects.create(community_id=community.pk, user=owner, role="admin")
    CommunityInvite.objects.filter(pk=snapshots[1][0]).update(revoked_at=None)
    current, _ = services.current_invitation(owner, community.pk)
    assert current is not None and current.pk in [x[0] for x in snapshots[1:]]
    assert services.valid_invite(snapshots[1][3])
    assert services.valid_invite(snapshots[2][3])
    services.invite(owner, community.pk)
    assert all(services.valid_invite(x[3]) is None for x in snapshots)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["rotate", "revoke", "remove", "double_rotate"])
def test_concurrent_invitation_operations(operation: str) -> None:
    owner, reader = member(), member("Reader")
    community = services.create(owner, "Amis")
    invitation = services.invite(owner, community.pk)
    services.join(reader, invitation.digest)
    barrier = Barrier(2)

    def run(which: int) -> str | None:
        try:
            barrier.wait(timeout=10)
            if which == 0:
                if operation in ("rotate", "double_rotate"):
                    return services.invite(owner, community.pk).digest
                if operation == "revoke":
                    services.revoke(owner, community.pk, invitation.pk)
                else:
                    services.remove(owner, community.pk, reader.pk)
            elif operation == "double_rotate":
                return services.invite(owner, community.pk).digest
            elif operation == "remove":
                try:
                    services.current_invitation(reader, community.pk)
                except Http404:
                    pass
            else:
                try:
                    services.join(reader, invitation.digest)
                except ValidationError:
                    pass
            return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [0, 1]))
    if operation == "remove":
        with pytest.raises(Http404):
            services.current_invitation(reader, community.pk)
    else:
        assert services.valid_invite(invitation.digest) is None
        assert CommunityInvite.objects.filter(
            community=community, revoked_at__isnull=True
        ).count() == (0 if operation == "revoke" else 1)


def test_signup_pending_invitation_is_invalidated_by_rotation(client: Client) -> None:
    from muqola.communities.models import PendingJoin
    from muqola.core.secrets import secret_cipher
    from muqola.identity.models import User

    owner = member()
    community = services.create(owner, "Amis")
    invitation = services.invite(owner, community.pk)
    raw = secret_cipher("community-invite").decrypt(invitation.encrypted_token.encode()).decode()
    client.get(reverse("communities:receive-invite", args=[raw]))
    client.post(
        reverse("identity:signup"),
        {
            "email": "signup-rotation@example.test",
            "display_name": "Invité",
            "password": "Fictif-Parcours-9847!",
            "password_confirm": "Fictif-Parcours-9847!",
            "adult_confirmed": True,
        },
    )
    user = User.objects.get(email="signup-rotation@example.test")
    assert PendingJoin.objects.get(user=user).digest == invitation.digest
    services.invite(owner, community.pk)
    user.email_verified_at = timezone.now()
    user.save()
    client.force_login(user)
    assert client.post(reverse("communities:join")).status_code == 400
    assert not Membership.objects.filter(user=user, community=community).exists()
