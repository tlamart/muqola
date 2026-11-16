from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.shortcuts import get_object_or_404

from muqola.catalogue.models import Game, GameAlias, GameReport, normalized_title
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User

FIELDS = {"title", "publisher", "year", "players_min", "players_max", "duration", "description"}


def title_condition(title: str, *, exact: bool = False) -> Q:
    key = normalized_title(title[:120])
    lookup = "title_key" if exact else "title_key__contains"
    aliases = GameAlias.objects.filter(game_id=OuterRef("pk"), **{lookup: key})
    return Q(**{lookup: key}) | Q(Exists(aliases))


def matching_title(query: QuerySet[Game], title: str, *, exact: bool = False) -> QuerySet[Game]:
    """Filtre sans autorisation implicite ; le lecteur doit déjà restreindre query."""
    return query.filter(title_condition(title, exact=exact)) if title or exact else query


def search(user: User, title: str = "") -> QuerySet[Game]:
    verified(user)
    return matching_title(Game.objects.filter(hidden=False).select_related("illustration"), title)


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
