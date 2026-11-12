import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.http import Http404
from django.test import Client
from django.urls import reverse

from muqola.communities import services as communities
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.loans import services as loans
from muqola.operations import services
from muqola.operations.models import OperatorAction
from tests.helpers import member
from tests.test_loans import scenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator_user() -> User:
    user = member("Operateur")
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    return user


@pytest.fixture
def orphaned_community(operator_user: User) -> tuple[Community, User]:
    alice, bob = member(), member("Bob")
    community = communities.create(alice, "Amis")
    Membership.objects.create(community=community, user=bob)
    services.disable_user(operator_user, alice.pk, "Compte désactivé")
    return community, bob


def test_explicit_operator_recovery_is_audited_and_preserves_private_data(
    operator_user: User, client: Client
) -> None:
    alice, bob, clara, community, copy = scenario()
    other = communities.create(clara, "Autre communauté")
    Membership.objects.create(community=other, user=bob)
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    services.disable_user(operator_user, alice.pk, "Compte désactivé")
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert communities.membership(clara, community.pk).role == Membership.Role.MEMBER
    assert not Membership.objects.filter(
        community=community, role=Membership.Role.ADMIN, active=True, user__is_active=True
    ).exists()
    with pytest.raises(Http404):
        communities.transfer(bob, community.pk, clara.pk)

    output = StringIO()
    call_command(
        "ops",
        "recover-community-admin",
        "--operator",
        operator_user.email,
        "--community-id",
        str(community.pk),
        "--user-id",
        str(bob.pk),
        "--reason",
        "  Reprise validée par l'opérateur  ",
        stdout=output,
    )
    assert json.loads(output.getvalue()) == {"status": "recorded"}
    assert communities.membership(bob, community.pk, admin=True).role == Membership.Role.ADMIN
    assert communities.membership(clara, community.pk).role == Membership.Role.MEMBER
    assert communities.membership(bob, other.pk).role == Membership.Role.MEMBER
    bob.refresh_from_db()
    alice.refresh_from_db()
    assert not bob.is_superuser and not bob.is_staff and not alice.is_active
    entry = OperatorAction.objects.get(action="recover_community_admin")
    assert entry.operator == operator_user
    assert entry.target == f"{community.pk}:{bob.pk}"
    assert entry.reason == "Reprise validée par l'opérateur" and entry.created_at is not None
    communities.update(bob, community.pk, "Communauté reprise", "")
    loan.refresh_from_db()
    copy.refresh_from_db()
    assert loan.state == "ACCEPTED" and copy.withdrawn
    client.force_login(operator_user)
    assert client.get(reverse("communities:detail", args=[community.pk])).status_code == 404
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 404


@pytest.mark.parametrize("actor_kind", ["member", "admin", "staff", "inactive", "unverified"])
def test_recovery_requires_an_active_verified_platform_operator(
    orphaned_community: tuple[Community, User], actor_kind: str
) -> None:
    community, bob = orphaned_community
    actor = member("Acteur", verified=actor_kind != "unverified")
    if actor_kind == "admin":
        communities.create(actor, "Communauté de l'acteur")
    actor.is_staff = actor_kind == "staff"
    actor.is_superuser = actor_kind in {"inactive", "unverified"}
    actor.is_active = actor_kind != "inactive"
    actor.save()
    with pytest.raises(PermissionDenied):
        services.recover_community_admin(actor, community.pk, bob.pk, "Reprise")
    with pytest.raises(CommandError, match="Opérateur non autorisé"):
        call_command(
            "ops",
            "recover-community-admin",
            operator=actor.email,
            community_id=community.pk,
            user_id=bob.pk,
            reason="Reprise",
        )
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


@pytest.mark.parametrize("target_kind", ["foreign", "removed", "inactive", "unverified"])
def test_recovery_does_not_create_or_reactivate_membership_or_account(
    operator_user: User, orphaned_community: tuple[Community, User], target_kind: str
) -> None:
    community, bob = orphaned_community
    if target_kind == "foreign":
        bob = member("Clara")
        communities.create(bob, "Autre")
    else:
        if target_kind == "removed":
            Membership.objects.filter(community=community, user=bob).update(active=False)
        elif target_kind == "inactive":
            User.objects.filter(pk=bob.pk).update(is_active=False)
        else:
            User.objects.filter(pk=bob.pk).update(email_verified_at=None)
    before = list(Membership.objects.order_by("pk").values())
    with pytest.raises(ValidationError):
        services.recover_community_admin(operator_user, community.pk, bob.pk, "Reprise")
    assert list(Membership.objects.order_by("pk").values()) == before
    bob.refresh_from_db()
    assert bob.is_active == (target_kind != "inactive")
    assert (bob.email_verified_at is not None) == (target_kind != "unverified")
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


def test_recovery_cannot_override_an_existing_usable_administrator(operator_user: User) -> None:
    alice, bob = member(), member("Bob")
    community = communities.create(alice, "Amis")
    Membership.objects.create(community=community, user=bob)
    with pytest.raises(ValidationError, match="déjà un administrateur"):
        services.recover_community_admin(operator_user, community.pk, bob.pk, "Reprise")
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


def test_repeated_recovery_cannot_promote_another_member(
    operator_user: User, orphaned_community: tuple[Community, User]
) -> None:
    community, bob = orphaned_community
    clara = member("Clara")
    Membership.objects.create(community=community, user=clara)
    services.recover_community_admin(operator_user, community.pk, bob.pk, "Reprise")
    for target in (bob, clara):
        with pytest.raises(ValidationError):
            services.recover_community_admin(operator_user, community.pk, target.pk, "Reprise")
    assert communities.membership(clara, community.pk).role == Membership.Role.MEMBER
    assert OperatorAction.objects.filter(action="recover_community_admin").count() == 1


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_recovery_requires_a_valid_reason_and_rolls_back(
    operator_user: User, orphaned_community: tuple[Community, User], reason: str
) -> None:
    community, bob = orphaned_community
    with pytest.raises(CommandError, match="Motif"):
        call_command(
            "ops",
            "recover-community-admin",
            operator=operator_user.email,
            community_id=community.pk,
            user_id=bob.pk,
            reason=reason,
        )
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


def test_recovery_is_rolled_back_if_audit_write_fails(
    operator_user: User, orphaned_community: tuple[Community, User]
) -> None:
    community, bob = orphaned_community
    with patch("muqola.operations.services.audit", side_effect=RuntimeError("Audit indisponible")):
        with pytest.raises(RuntimeError, match="Audit indisponible"):
            services.recover_community_admin(operator_user, community.pk, bob.pk, "Reprise")
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


@pytest.mark.parametrize("missing", ["community_id", "user_id"])
def test_recovery_requires_both_explicit_target_identifiers(
    operator_user: User, orphaned_community: tuple[Community, User], missing: str
) -> None:
    community, bob = orphaned_community
    options = {"community_id": str(community.pk), "user_id": str(bob.pk)}
    del options[missing]
    args = [
        arg for name, value in options.items() for arg in (f"--{name.replace('_', '-')}", value)
    ]
    with pytest.raises(CommandError, match="--community-id et --user-id"):
        call_command(
            "ops",
            "recover-community-admin",
            "--operator",
            operator_user.email,
            "--reason",
            "Reprise",
            *args,
        )
    assert communities.membership(bob, community.pk).role == Membership.Role.MEMBER
    assert not OperatorAction.objects.filter(action="recover_community_admin").exists()


def test_recovery_of_nonexistent_community_is_refused(operator_user: User) -> None:
    with pytest.raises(ValidationError):
        services.recover_community_admin(operator_user, uuid4(), operator_user.pk, "Reprise")
    assert not OperatorAction.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_recoveries_promote_only_one_member(
    operator_user: User, orphaned_community: tuple[Community, User]
) -> None:
    community, bob = orphaned_community
    clara = member("Clara")
    Membership.objects.create(community=community, user=clara)
    barrier = Barrier(2)

    def recover(target: User) -> bool:
        try:
            barrier.wait(timeout=10)
            services.recover_community_admin(operator_user, community.pk, target.pk, "Reprise")
            return True
        except ValidationError:
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(recover, [bob, clara])) == 1
    assert (
        Membership.objects.filter(
            community=community,
            active=True,
            role=Membership.Role.ADMIN,
            user__is_active=True,
            user__email_verified_at__isnull=False,
        ).count()
        == 1
    )
    assert OperatorAction.objects.filter(action="recover_community_admin").count() == 1
