from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

from muqola.catalogue.matching import matching_title as matching_title
from muqola.catalogue.matching import ranked
from muqola.catalogue.matching import title_condition as title_condition
from muqola.catalogue.models import Game, GameReport, normalized_title
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User

FIELDS = {
    "title",
    "publisher",
    "year",
    "players_min",
    "players_max",
    "duration",
    "description",
    "kind",
    "base_game_id",
}


def search(user: User, title: str = "") -> QuerySet[Game]:
    verified(user)
    return ranked(
        Game.objects.filter(
            hidden=False, merged_into__isnull=True, moderation_status=Game.Status.APPROVED
        ).select_related("illustration"),
        title,
    )


def readable(user: User) -> QuerySet[Game]:
    verified(user)
    from muqola.inventory.services import visible

    accessible_game_ids = visible(user).values("game_id")
    permission = Q(moderation_status=Game.Status.APPROVED) | Q(created_by=user)
    permission |= Q(moderation_status=Game.Status.PENDING, pk__in=accessible_game_ids)
    permission |= Q(moderation_status=Game.Status.LEGACY) & (
        Q(pk__in=accessible_game_ids) | Q(merged_into_id__in=accessible_game_ids)
    )
    if user.is_superuser:
        permission = Q()
    return Game.objects.filter(permission, hidden=False).select_related("illustration", "base_game")


def canonical(user: User, game_id: UUID) -> Game:
    game = get_object_or_404(readable(user), pk=game_id)
    seen = set()
    while game.merged_into_id:
        if game.pk in seen:
            raise ValidationError("Référence de fusion invalide.")
        seen.add(game.pk)
        game = get_object_or_404(readable(user), pk=game.merged_into_id)
    return game


def write_game(user: User, data: dict[str, Any], game_id: UUID | None = None) -> Game:
    """Create/update a proposal without granting catalogue-wide visibility."""
    with domain_write(user):
        game = (
            Game(created_by=user)
            if game_id is None
            else get_object_or_404(
                Game,
                pk=game_id,
                created_by=user,
                hidden=False,
                merged_into__isnull=True,
            )
        )
        if (
            game.moderation_status not in (Game.Status.PENDING, Game.Status.REJECTED)
            or game.ever_reused
        ):
            raise ValidationError(
                "Les corrections de cette fiche passent par la maintenance. "
                "Utilisez le signalement."
            )
        for key in FIELDS:
            if key in data:
                value = data[key]
                setattr(game, key, value.strip() if isinstance(value, str) else value)
        game.proposal_reason = str(data.get("proposal_reason", game.proposal_reason)).strip()
        if not isinstance(game.title, str):
            raise ValidationError("Le titre doit être du texte.")
        game.title_key = normalized_title(game.title)
        # Suggestions reveal approved metadata only, never another user's proposal.
        if (
            matching_title(search(user), game.title, exact=True).exclude(pk=game.pk).exists()
            and not game.proposal_reason
        ):
            raise ValidationError(
                "Un jeu de ce nom existe déjà. Sélectionnez-le ou expliquez "
                "pourquoi il s'agit d'un jeu distinct, pas d'une autre édition."
            )
        if (
            matching_title(
                Game.objects.filter(
                    created_by=user,
                    moderation_status__in=[Game.Status.PENDING, Game.Status.REJECTED],
                    merged_into__isnull=True,
                ),
                game.title,
                exact=True,
            )
            .exclude(pk=game.pk)
            .exists()
        ):
            raise ValidationError("Vous avez déjà proposé ce titre. Consultez vos propositions.")
        # An author correction must not lift an operator rejection now that
        # pending copies can be lent. Only an explicit operator decision can.
        if game.moderation_status != Game.Status.REJECTED:
            game.moderation_status = Game.Status.PENDING
        if game.base_game_id and not search(user).filter(pk=game.base_game_id).exists():
            raise ValidationError("Choisissez un jeu de base validé.")
        game.full_clean()
        game.save()
        from muqola.catalogue.moderation import add_aliases, duplicates

        add_aliases(game, data.get("aliases", []))
        if (
            duplicates(game).filter(moderation_status=Game.Status.APPROVED, hidden=False).exists()
            and not game.proposal_reason
        ):
            raise ValidationError(
                "Un titre alternatif correspond déjà à une fiche : réutilisez-la "
                "ou justifiez un jeu distinct."
            )
        if (
            duplicates(game)
            .filter(
                created_by=user, moderation_status__in=[Game.Status.PENDING, Game.Status.REJECTED]
            )
            .exists()
        ):
            raise ValidationError(
                "Vous avez déjà proposé un titre équivalent. Consultez vos propositions."
            )
        return game


def report(user: User, game_id: UUID, reason: str) -> None:
    with domain_write(user):
        game = canonical(user, game_id)
        entry = GameReport.objects.filter(
            game=game, created_by=user, resolved_at__isnull=True
        ).first()
        entry = entry or GameReport(game=game, original_game=game, created_by=user)
        entry.reason = reason.strip()
        entry.full_clean()
        entry.save()
