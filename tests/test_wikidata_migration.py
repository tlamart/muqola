from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from muqola.catalogue.models import Game, GameAlias, GameIllustration
from muqola.inventory.models import OwnedGame
from muqola.loans.models import Loan


@pytest.mark.django_db(transaction=True)
def test_additive_migration_preserves_existing_game_copy_and_accepted_loan() -> None:
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [(app, "0001_initial" if app == "catalogue" else name) for app, name in latest]
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        User = apps.get_model("identity", "User")
        OldGame = apps.get_model("catalogue", "Game")
        OldCopy = apps.get_model("inventory", "OwnedGame")
        OldLoan = apps.get_model("loans", "Loan")
        owner = User.objects.create(
            email="migration-owner@example.test",
            display_name="Propriétaire",
            password="!",
            email_verified_at=timezone.now(),
        )
        borrower = User.objects.create(
            email="migration-borrower@example.test",
            display_name="Emprunteur",
            password="!",
            email_verified_at=timezone.now(),
        )
        game = OldGame.objects.create(
            title="Titre humain préservé",
            title_key="titre humain preserve",
            created_by=owner,
            hidden=True,
        )
        copy = OldCopy.objects.create(game=game, owner=owner, notes="Notes privées", withdrawn=True)
        loan = OldLoan.objects.create(
            owned_game=copy,
            owner=owner,
            borrower=borrower,
            due_date=date(2099, 1, 1),
            state="ACCEPTED",
        )
    finally:
        MigrationExecutor(connection).migrate(latest)
    migrated_game = Game.objects.get(pk=game.pk)
    migrated_copy = OwnedGame.objects.get(pk=copy.pk)
    assert migrated_game.title == "Titre humain préservé" and migrated_game.hidden
    assert migrated_game.data_source == migrated_game.data_license == migrated_game.bgg_ids == ""
    assert migrated_copy.notes == "Notes privées" and migrated_copy.withdrawn
    assert migrated_copy.owner_id == owner.pk and migrated_copy.game_id == game.pk
    assert Loan.objects.get(pk=loan.pk).state == "ACCEPTED"
    assert not GameAlias.objects.exists() and not GameIllustration.objects.exists()
