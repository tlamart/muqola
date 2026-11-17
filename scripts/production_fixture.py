"""Synthetic-only fixture, invoked exclusively by production_smoke."""

# ruff: noqa: S106 -- synthetic users have unusable passwords

import os

if os.environ.get("MUQOLA_SYNTHETIC_TEST") != "lot6-isolated":
    raise RuntimeError("Synthetic test context required")

from datetime import date

from django.utils import timezone

from muqola.catalogue.models import Game, GameAlias, GameIllustration
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.loans.models import Loan

owner = User.objects.create(
    email="owner@example.test",
    display_name="Synthetic owner",
    password="!",
    email_verified_at=timezone.now(),
    adult_confirmed_at=timezone.now(),
)
reader = User.objects.create(
    email="reader@example.test",
    display_name="Synthetic reader",
    password="!",
    email_verified_at=timezone.now(),
    adult_confirmed_at=timezone.now(),
)
game = Game.objects.create(
    title="Synthetic backup game", title_key="synthetic backup game", created_by=owner
)
GameAlias.objects.create(game=game, title="Synthetic alias", title_key="synthetic alias")
GameIllustration.objects.create(
    game=game,
    image_url="https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic.jpg",
    commons_file="File:Synthetic.jpg",
    source_url="https://commons.wikimedia.org/wiki/File:Synthetic.jpg",
    license="CC0",
    license_url="https://creativecommons.org/publicdomain/zero/1.0",
    artist="Synthetic credit",
)
community = Community.objects.create(name="Synthetic private group", created_by=owner)
Membership.objects.create(community=community, user=owner, role="admin")
Membership.objects.create(community=community, user=reader)
for state in Loan.State.values:
    copy = OwnedGame.objects.create(game=game, owner=owner, notes="Synthetic private notes")
    GameVisibility.objects.create(owned_game=copy, community=community)
    Loan.objects.create(
        owned_game=copy, owner=owner, borrower=reader, state=state, due_date=date(2099, 1, 1)
    )
