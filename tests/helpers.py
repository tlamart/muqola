from typing import Any
from uuid import UUID

from django.utils import timezone

from muqola.catalogue.models import Game
from muqola.identity.models import User


def member(name: str = "Alice", verified: bool = True) -> User:
    return User.objects.create(
        email=f"{name.lower()}@example.test",
        display_name=name,
        email_verified_at=timezone.now() if verified else None,
        adult_confirmed_at=timezone.now(),
        password="!",
    )


def catalogue_operator() -> User:
    user, _ = User.objects.get_or_create(
        email="catalogue-operator@example.test",
        defaults={
            "display_name": "Opérateur synthétique",
            "password": "!",
            "is_superuser": True,
            "email_verified_at": timezone.now(),
            "adult_confirmed_at": timezone.now(),
        },
    )
    return user


def approved_game(user: User, data: dict[str, Any], game_id: UUID | None = None) -> Game:
    """Regression fixture: public games now require an actual operator decision."""
    from muqola.catalogue.moderation import decide
    from muqola.catalogue.services import write_game

    if game_id is not None:
        return write_game(user, data, game_id)
    game = write_game(user, {"proposal_reason": "Jeu synthétique distinct pour les tests", **data})
    return decide(
        catalogue_operator(),
        game.pk,
        Game.Status.APPROVED,
        "Validation de données synthétiques",
        {"kind": "standalone", "external_ids": data.get("external_ids", [])},
        "Homonymie synthétique explicitement testée",
    )
