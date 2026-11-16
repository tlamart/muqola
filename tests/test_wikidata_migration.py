"""Exercise the historical #25 and new B migrations in isolated synthetic schemas."""

from datetime import date
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from muqola.catalogue.models import (
    Game,
    GameAlias,
    GameExternalIdentifier,
    GameIllustration,
    GameReport,
)
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.loans.models import Loan


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("previous", ["0001_initial", "0002_wikidata_catalogue"])
def test_additive_migrations_preserve_all_references_and_loan_states(previous: str) -> None:
    # The live test schema cannot be downgraded after B. Build an entirely new one.
    schema = connection.ops.quote_name("pr_b_synthetic_" + uuid4().hex)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {schema}")
        cursor.execute(f"SET search_path TO {schema}")
    try:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [(app, previous if app == "catalogue" else name) for app, name in latest]
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        User = apps.get_model("identity", "User")
        OldGame = apps.get_model("catalogue", "Game")
        OldCopy = apps.get_model("inventory", "OwnedGame")
        OldLoan = apps.get_model("loans", "Loan")
        Community = apps.get_model("communities", "Community")
        Membership = apps.get_model("communities", "Membership")
        Visibility = apps.get_model("inventory", "GameVisibility")
        Report = apps.get_model("catalogue", "GameReport")
        owner = User.objects.create(
            email="migration-owner@example.test",
            display_name="Propriétaire",
            password="!",
            is_superuser=True,
            email_verified_at=timezone.now(),
        )
        borrower = User.objects.create(
            email="migration-borrower@example.test",
            display_name="Emprunteur",
            password="!",
            email_verified_at=timezone.now(),
        )
        games = [
            OldGame.objects.create(
                title="Titre humain préservé",
                title_key="titre humain preserve",
                created_by=owner,
                hidden=hidden,
                ever_reused=True,
                external_source="synthetic",
                external_id=str(hidden),
            )
            for hidden in (False, True)
        ]
        community = Community.objects.create(name="Synthétique", created_by=owner)
        Membership.objects.create(community=community, user=owner, role="admin")
        Membership.objects.create(community=community, user=borrower)
        for index, state in enumerate(Loan.State.values):
            copy = OldCopy.objects.create(
                game=games[index % 2],
                owner=owner,
                notes="Notes privées",
                withdrawn=index % 2 == 1,
                archived=state == "RETURNED",
            )
            Visibility.objects.create(owned_game=copy, community=community)
            OldLoan.objects.create(
                owned_game=copy,
                owner=owner,
                borrower=borrower,
                due_date=date(2099, 1, 1),
                state=state,
            )
        private = OldCopy.objects.create(game=games[0], owner=owner, notes="Privé")
        for game in games:
            Report.objects.create(game=game, created_by=owner, reason="Signalement synthétique")
        if previous == "0002_wikidata_catalogue":
            games[0].bgg_ids = "987;" + "9" * 121
            games[0].save()
            games[1].external_source, games[1].external_id = "bgg", "987"
            games[1].save()
            Alias = apps.get_model("catalogue", "GameAlias")
            Image = apps.get_model("catalogue", "GameIllustration")
            Alias.objects.create(
                game=games[0], title="Alias synthétique", title_key="alias synthetique"
            )
            Image.objects.create(
                game=games[0],
                image_url="https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg",
                commons_file="File:Synthetic game.jpg",
                source_url="https://commons.wikimedia.org/wiki/File:Synthetic_game.jpg",
                license="CC0",
                license_url="https://creativecommons.org/publicdomain/zero/1.0",
                artist="Crédit conservé",
            )
        before = {
            "copies": list(OldCopy.objects.order_by("pk").values()),
            "loans": list(OldLoan.objects.order_by("pk").values()),
            "visibility": list(Visibility.objects.order_by("pk").values()),
            "reports": list(Report.objects.order_by("pk").values()),
        }
        from muqola.catalogue.moderation import inventory

        before_inventory = inventory(owner)
        assert before_inventory["schema"] == "before_refonte_b"
        assert before_inventory["games"] == 2 and before_inventory["copies"] == 7
        assert before_inventory["references"]
        # Tables/recorder now exist in our isolated schema; pg_trgm lives in public.
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}, public")
        MigrationExecutor(connection).migrate(latest)
        assert list(OwnedGame.objects.order_by("pk").values()) == before["copies"]
        assert list(Loan.objects.order_by("pk").values()) == before["loans"]
        assert list(GameVisibility.objects.order_by("pk").values()) == before["visibility"]
        assert OwnedGame.objects.get(pk=private.pk).visibilities.count() == 0
        assert Game.objects.count() == len(games)
        assert set(Game.objects.values_list("moderation_status", flat=True)) == {"legacy_to_review"}
        assert set(Game.objects.values_list("kind", flat=True)) == {"unknown"}
        assert Game.objects.get(pk=games[1].pk).hidden
        assert Game.objects.get(pk=games[0].pk).ever_reused
        assert GameExternalIdentifier.objects.count() == 2
        for row in before["reports"]:
            migrated = dict(GameReport.objects.values().get(pk=row["id"]))
            assert migrated.pop("original_game_id") == row["game_id"]
            assert migrated == row
        if previous == "0002_wikidata_catalogue":
            assert (
                GameExternalIdentifier.objects.get(source="bgg", identifier="987").game_id
                == games[1].pk
            )
            assert Game.objects.get(pk=games[0].pk).bgg_ids == "987;" + "9" * 121
            assert GameAlias.objects.get().title == "Alias synthétique"
            assert GameIllustration.objects.get().artist == "Crédit conservé"
        else:
            assert not GameAlias.objects.exists() and not GameIllustration.objects.exists()
        with pytest.raises(IrreversibleError):
            MigrationExecutor(connection).migrate(old)
        assert Game.objects.count() == 2 and OwnedGame.objects.count() == 7
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            # Only the schema created by this test in its disposable database is removed.
            cursor.execute(f"DROP SCHEMA {schema} CASCADE")
