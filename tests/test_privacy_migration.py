from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_additive_privacy_migrations_preserve_every_loan_state_and_do_not_erase_accounts() -> None:
    schema = connection.ops.quote_name("privacy_synthetic_" + uuid4().hex)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {schema}")
        cursor.execute(f"SET search_path TO {schema}")
    try:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous_names = {
            "identity": "0003_user_adult_confirmed_at",
            "communities": "0002_invitationevent_and_more",
            "operations": "0001_initial",
            "catalogue": "0002_wikidata_catalogue",
        }
        previous = [(app, previous_names.get(app, name)) for app, name in latest]
        executor.migrate(previous)
        state = executor.loader.project_state(previous).apps
        User = state.get_model("identity", "User")
        Game = state.get_model("catalogue", "Game")
        Copy = state.get_model("inventory", "OwnedGame")
        Loan = state.get_model("loans", "Loan")
        Community = state.get_model("communities", "Community")
        alice = User.objects.create(
            email="alice@example.test", display_name="Synthetic", password="!"
        )
        bob = User.objects.create(email="bob@example.test", display_name="Synthetic", password="!")
        game = Game.objects.create(title="Synthetic", title_key="synthetic", created_by=alice)
        community = Community.objects.create(name="Synthetic", created_by=alice)
        for loan_state in [
            "REQUESTED",
            "ACCEPTED",
            "HANDED_OVER",
            "RETURNED",
            "DECLINED",
            "CANCELLED",
        ]:
            copy = Copy.objects.create(game=game, owner=alice, notes="Synthetic notes")
            Loan.objects.create(
                owned_game=copy,
                owner=alice,
                borrower=bob,
                state=loan_state,
                due_date=timezone.now().date() + timedelta(days=3),
            )
        before = list(Loan.objects.order_by("pk").values())
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}, public")
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        assert list(current.get_model("loans", "Loan").objects.order_by("pk").values()) == before
        assert current.get_model("identity", "User").objects.count() == 2
        assert (
            current.get_model("identity", "User")
            .objects.filter(deletion_restricted_at__isnull=False)
            .count()
            == 0
        )
        assert (
            current.get_model("communities", "Community").objects.get(pk=community.pk).archived_at
            is None
        )
        assert current.get_model("catalogue", "Game").objects.filter(pk=game.pk).exists()
        assert current.get_model("operations", "PrivacyReceipt").objects.count() == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")
