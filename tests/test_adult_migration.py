"""The additive adult gate neither erases history nor invents consent."""

from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_accounts_remain_unattested_and_references_are_preserved() -> None:
    schema = connection.ops.quote_name("adult_synthetic_" + uuid4().hex)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {schema}")
        cursor.execute(f"SET search_path TO {schema}")
    try:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [
            (
                app,
                "0002_accounttoken_ratebucket_alter_user_options_and_more"
                if app == "identity"
                else "0002_wikidata_catalogue"
                if app == "catalogue"
                else name,
            )
            for app, name in latest
        ]
        executor.migrate(previous)
        User = executor.loader.project_state(previous).apps.get_model("identity", "User")
        user = User.objects.create(
            email="legacy@example.test", display_name="Synthetic legacy", password="!"
        )
        before = list(User.objects.values())
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}, public")
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        CurrentUser = executor.loader.project_state(latest).apps.get_model("identity", "User")
        current = CurrentUser.objects.values().get(pk=user.pk)
        assert current.pop("adult_confirmed_at") is None
        assert current == before[0]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")
