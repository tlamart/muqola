"""Promotion automation uses the same transactional checks and mandatory audit."""

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import override_settings
from django.utils import timezone

from muqola.identity.models import User
from muqola.operations.models import OperatorAction
from tests.helpers import member

pytestmark = pytest.mark.django_db


def candidate(name: str = "Cible") -> User:
    user = member(name)
    user.set_password("Mot-De-Passe-Synthetique-456!")
    user.save()
    return user


def promotion(user: User, **changes: Any) -> dict[str, Any]:
    output = StringIO()
    options = {
        "email": user.email,
        "confirm_email": user.email,
        "reason": "Habilitation ponctuelle synthétique",
        "bootstrap": True,
        "if_needed": True,
        "json": True,
        **changes,
    }
    if not options["bootstrap"]:
        del options["bootstrap"]
    call_command("promote_operator", stdout=output, **options)
    value = output.getvalue()
    assert user.email not in value
    assert user.password not in value
    assert str(options["reason"]) not in value
    result: dict[str, Any] = json.loads(value)
    return result


def test_real_preview_does_not_write_any_user_field_or_audit() -> None:
    user = candidate()
    before = list(User.objects.values())
    assert promotion(user, dry_run=True) == {
        "status": "would_promote",
        "dry_run": True,
        "environment": "test",
    }
    assert list(User.objects.values()) == before
    assert not OperatorAction.objects.exists()


def test_repeated_promotion_is_a_noop_with_authorization_rechecked() -> None:
    user = candidate()
    assert promotion(user)["status"] == "promoted"
    user.refresh_from_db()
    assert user.is_staff and user.is_superuser
    before = list(User.objects.values())
    audit = list(OperatorAction.objects.values())
    assert len(audit) == 1
    assert audit[0]["action"] == "bootstrap_operator"
    for dry_run in (False, True):
        assert promotion(user, dry_run=dry_run)["status"] == "unchanged"
        assert list(User.objects.values()) == before
        assert list(OperatorAction.objects.values()) == audit
    outsider = candidate("Tiers")
    with pytest.raises(CommandError):
        promotion(user, bootstrap=False, operator=outsider.email)
    assert list(OperatorAction.objects.values()) == audit


def test_subsequent_promotion_uses_existing_operator_and_remains_idempotent() -> None:
    actor, user = candidate("Acteur"), candidate()
    promotion(actor)
    assert promotion(user, bootstrap=False, operator=actor.email, dry_run=True)["status"] == (
        "would_promote"
    )
    assert OperatorAction.objects.count() == 1
    assert promotion(user, bootstrap=False, operator=actor.email)["status"] == "promoted"
    assert promotion(user, bootstrap=False, operator=actor.email)["status"] == "unchanged"
    assert OperatorAction.objects.count() == 2
    assert OperatorAction.objects.latest("created_at").operator_id == actor.pk
    # Idempotence must not turn bootstrap into a recovery/force option.
    with pytest.raises(CommandError):
        promotion(actor)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "fault", ["inactive", "unverified", "adult_missing", "unusable", "restricted", "reason"]
)
def test_automation_preserves_all_target_guards(fault: str, dry_run: bool) -> None:
    user = candidate()
    if fault == "inactive":
        user.is_active = False
    elif fault == "unverified":
        user.email_verified_at = None
    elif fault == "adult_missing":
        user.adult_confirmed_at = None
    elif fault == "unusable":
        user.set_unusable_password()
    elif fault == "restricted":
        user.deletion_restricted_at = timezone.now()
    user.save()
    before = list(User.objects.values())
    with pytest.raises(CommandError):
        promotion(user, dry_run=dry_run, reason=" " if fault == "reason" else "Motif valide")
    assert list(User.objects.values()) == before
    assert not OperatorAction.objects.exists()


@pytest.mark.parametrize("fault", ["inactive", "unverified", "adult_missing", "restricted"])
def test_noop_does_not_bypass_actor_permissions(fault: str) -> None:
    actor, user = candidate("Acteur"), candidate()
    promotion(actor)
    promotion(user, bootstrap=False, operator=actor.email)
    if fault == "inactive":
        actor.is_active = False
    elif fault == "unverified":
        actor.email_verified_at = None
    elif fault == "adult_missing":
        actor.adult_confirmed_at = None
    else:
        actor.deletion_restricted_at = timezone.now()
    actor.save()
    with pytest.raises(CommandError):
        promotion(user, bootstrap=False, operator=actor.email)
    assert OperatorAction.objects.count() == 2


def test_dry_run_enforces_bootstrap_confirmation_and_audit_reason() -> None:
    actor, user = candidate("Acteur"), candidate()
    promotion(actor)
    with pytest.raises(CommandError):
        promotion(user, dry_run=True)
    with pytest.raises(CommandError):
        promotion(
            user, bootstrap=False, operator=actor.email, confirm_email=actor.email, dry_run=True
        )
    with pytest.raises(CommandError):
        promotion(user, bootstrap=False, operator=actor.email, reason="x" * 501, dry_run=True)
    assert OperatorAction.objects.count() == 1


def test_audit_failure_rolls_back_automated_promotion() -> None:
    user = candidate()
    before = list(User.objects.values())
    with patch(
        "muqola.operations.services.OperatorAction.objects.create", side_effect=RuntimeError
    ):
        with pytest.raises(RuntimeError):
            promotion(user)
    assert list(User.objects.values()) == before
    assert not OperatorAction.objects.exists()


@pytest.mark.parametrize("expected", ["production", "staging"])
def test_requested_environment_is_verified_before_account_lookup(expected: str) -> None:
    user = candidate()
    for app_env, deployment_env in (("test", expected), ("production", "test")):
        with override_settings(APP_ENV=app_env, DEPLOYMENT_ENV=deployment_env):
            with patch.object(User.objects, "filter", side_effect=AssertionError("DB accessed")):
                with pytest.raises(CommandError, match="contexte applicatif"):
                    promotion(user, deployment_env=expected, dry_run=True)
    with override_settings(APP_ENV="production", DEPLOYMENT_ENV=expected):
        assert promotion(user, deployment_env=expected, dry_run=True)["environment"] == expected
    assert not OperatorAction.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_idempotent_bootstrap_grants_and_audits_only_once() -> None:
    user = candidate()
    barrier = Barrier(2)

    def execute(_: int) -> str:
        try:
            barrier.wait(timeout=10)
            return str(promotion(user)["status"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(execute, range(2))) == ["promoted", "unchanged"]
    assert User.objects.filter(is_superuser=True, is_staff=True).count() == 1
    assert OperatorAction.objects.count() == 1
