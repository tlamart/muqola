from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from muqola.catalogue.models import Game, GameReport, normalized_title
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User

FIELDS = {"title", "publisher", "year", "players_min", "players_max", "duration", "description"}


def search(user: User, title: str = "") -> QuerySet[Game]:
    verified(user)
    return Game.objects.filter(hidden=False, title_key__contains=normalized_title(title[:120]))


def write_game(user: User, data: dict[str, Any], game_id: UUID | None = None) -> Game:
    with domain_write(user):
        game = (
            Game(created_by=user)
            if game_id is None
            else get_object_or_404(Game, pk=game_id, created_by=user, hidden=False)
        )
        if game.ever_reused:
            raise ValidationError(
                "Les corrections de cette fiche passent désormais par la maintenance. "
                "Utilisez le signalement."
            )
        for key in FIELDS:
            if key in data:
                setattr(game, key, data[key].strip() if isinstance(data[key], str) else data[key])
        game.title_key = normalized_title(game.title)
        game.full_clean()
        game.save()
        return game


def report(user: User, game_id: UUID, reason: str) -> None:
    with domain_write(user):
        game = get_object_or_404(Game, pk=game_id, hidden=False)
        entry = GameReport.objects.filter(
            game=game, created_by=user, resolved_at__isnull=True
        ).first()
        entry = entry or GameReport(game=game, created_by=user)
        entry.reason = reason.strip()
        entry.full_clean()
        entry.save()
