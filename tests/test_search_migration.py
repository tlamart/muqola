"""A is additive on populated B, and runtime needs no extension privileges."""

from uuid import uuid4

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from muqola.catalogue.models import Game, GameAlias
from muqola.catalogue.services import search
from muqola.inventory.models import OwnedGame
from tests.helpers import member


@pytest.mark.django_db(transaction=True)
def test_populated_b_migrates_without_changing_rows() -> None:
    schema = connection.ops.quote_name("pr_a_synthetic_" + uuid4().hex)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {schema}")
        cursor.execute(f"SET search_path TO {schema}")
    try:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [
            (
                app,
                "0003_gamedecision_gameexternalidentifier_gamemerge_and_more"
                if app == "catalogue"
                else name,
            )
            for app, name in latest
        ]
        executor.migrate(previous)
        owner = member()
        game = Game.objects.create(title="Étoiles synthétiques", created_by=owner)
        GameAlias.objects.create(game=game, title="Constellation fictive")
        OwnedGame.objects.create(game=game, owner=owner, notes="Privé conservé")
        before = [list(model.objects.values()) for model in (Game, GameAlias, OwnedGame)]
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}, public")
        MigrationExecutor(connection).migrate(latest)
        assert [list(model.objects.values()) for model in (Game, GameAlias, OwnedGame)] == before
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s", [schema.strip('"')]
            )
            indexes = {row[0] for row in cursor.fetchall()}
        assert {"game_title_trgm", "alias_title_trgm"} <= indexes
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.mark.django_db
def test_runtime_search_with_unprivileged_role() -> None:
    owner = member()
    target = Game.objects.create(
        title="Régicide",
        created_by=owner,
        moderation_status=Game.Status.APPROVED,
        kind=Game.Kind.STANDALONE,
    )
    role = connection.ops.quote_name("search_runtime_" + uuid4().hex)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOCREATEDB NOCREATEROLE NOLOGIN")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        cursor.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
        cursor.execute(f"SET LOCAL ROLE {role}")
    try:
        assert search(owner, "regicdie").get() == target
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION unaccent")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@pytest.mark.django_db
def test_benchmark_refuses_normal_or_populated_database() -> None:
    from io import StringIO
    from unittest.mock import patch

    from django.core.management import CommandError, call_command

    owner = member()
    target = Game.objects.create(title="Préservé", created_by=owner)
    with pytest.raises(CommandError, match="dédiée"):
        call_command("benchmark_search", stdout=StringIO())
    # Changing the declared name does not reconnect: test only the pre-write guard.
    with patch.dict(connection.settings_dict, {"NAME": "guard_synthetic_benchmark"}):
        with pytest.raises(CommandError, match="vide"):
            call_command("benchmark_search", stdout=StringIO())
    assert Game.objects.get().pk == target.pk
