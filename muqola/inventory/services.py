from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from muqola.catalogue.models import Game
from muqola.communities.models import Membership
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User
from muqola.inventory.models import GameVisibility, OwnedGame

if TYPE_CHECKING:
    from django_stubs_ext import WithAnnotations


class Availability(TypedDict):
    has_active_loan: bool


def with_availability(
    query: QuerySet[OwnedGame],
) -> QuerySet[WithAnnotations[OwnedGame, Availability]]:
    from muqola.loans.models import Loan

    return query.annotate(
        has_active_loan=Exists(
            Loan.objects.filter(owned_game_id=OuterRef("pk"), state__in=["ACCEPTED", "HANDED_OVER"])
        )
    )


def visible(user: User) -> QuerySet[OwnedGame]:
    return (
        with_availability(OwnedGame.objects.filter(archived=False))
        .filter(Q(owner=user) | Q(pk__in=borrowable(user).values("pk")))
        .select_related("game", "game__illustration", "owner")
        .distinct()
    )


def borrowable(user: User, community_id: str = "") -> QuerySet[OwnedGame]:
    """Copies in a CURRENT common community, excluding the reader's collection.

    Two correlated membership tests cover the reader and the owner; neither a
    stale visibility nor an inactive owner can leak a copy. No joining duplicate
    edges, including copies shared in several communities.
    """
    verified(user)
    common = GameVisibility.objects.filter(
        owned_game_id=OuterRef("pk"),
        community_id__in=Membership.objects.filter(user=user, active=True).values("community_id"),
    ).filter(
        community_id__in=Membership.objects.filter(
            user_id=OuterRef("owned_game__owner_id"), active=True
        ).values("community_id")
    )
    if community_id:
        common = common.filter(community_id=community_id)
    return with_availability(
        OwnedGame.objects.filter(
            archived=False,
            withdrawn=False,
            owner__is_active=True,
            owner__email_verified_at__isnull=False,
            game__hidden=False,
            game__merged_into__isnull=True,
            game__moderation_status__in=[Game.Status.APPROVED, Game.Status.LEGACY],
        )
        .exclude(owner=user)
        .filter(Exists(common))
    ).select_related("game", "game__illustration", "owner")


def grouped(copies: QuerySet[OwnedGame], title: str = "") -> QuerySet[Game]:
    from muqola.catalogue.matching import ranked

    scoped = copies.order_by().filter(game_id=OuterRef("pk"))
    counts = scoped.values("game_id").annotate(total=Count("pk"))
    available_counts = (
        with_availability(scoped)
        .filter(has_active_loan=False)
        .values("game_id")
        .annotate(total=Count("pk"))
    )
    return (
        ranked(Game.objects.filter(pk__in=copies.order_by().values("game_id")), title)
        .annotate(
            copy_count=Coalesce(Subquery(counts.values("total")), 0, output_field=IntegerField()),
            available_count=Coalesce(
                Subquery(available_counts.values("total")), 0, output_field=IntegerField()
            ),
        )
        .select_related("illustration")
    )


def available(query: QuerySet[OwnedGame]) -> QuerySet[OwnedGame]:
    return with_availability(query).filter(
        withdrawn=False,
        archived=False,
        game__hidden=False,
        game__merged_into__isnull=True,
        game__moderation_status__in=[Game.Status.APPROVED, Game.Status.LEGACY],
        has_active_loan=False,
    )


def write_copy(
    user: User,
    game_id: UUID,
    notes: str,
    community_ids: list[UUID],
    withdrawn: bool = False,
    copy_id: UUID | None = None,
) -> OwnedGame:
    with domain_write(user):
        if copy_id is None:
            game = get_object_or_404(Game, pk=game_id, hidden=False, merged_into__isnull=True)
            if game.moderation_status != Game.Status.APPROVED and not (
                game.moderation_status == Game.Status.PENDING and game.created_by_id == user.pk
            ):
                from django.http import Http404

                raise Http404
            item = OwnedGame(game=game, owner=user)
        else:
            item = get_object_or_404(
                OwnedGame.objects.select_related("game"), pk=copy_id, owner=user, archived=False
            )
            game = item.game
        if item.game_id != game_id:
            raise ValidationError("La fiche d'un exemplaire ne peut pas être remplacée.")
        allowed = set(
            Membership.objects.filter(user=user, active=True).values_list("community_id", flat=True)
        )
        if not set(community_ids) <= allowed:
            raise ValidationError("Choisissez uniquement vos communautés actuelles.")
        if game.moderation_status in (Game.Status.PENDING, Game.Status.REJECTED) and community_ids:
            raise ValidationError(
                "Une proposition reste privée jusqu'à validation. Partagez votre "
                "exemplaire ensuite."
            )
        # L'édition privée ne peut pas annuler le retrait imposé par la modération.
        item.notes, item.withdrawn = notes.strip(), withdrawn or game.hidden
        item.full_clean()
        item.save()
        if game.created_by_id != user.pk:
            game.ever_reused = True
            game.save()
        item.visibilities.exclude(community_id__in=community_ids).delete()
        for community_id in set(community_ids):
            GameVisibility.objects.get_or_create(owned_game=item, community_id=community_id)
        from muqola.loans.services import close_ineligible_requests

        close_ineligible_requests(user, copy_id=item.pk)
        return item


def remove_community_visibility(user_id: int, community_id: UUID) -> None:
    # Appelé dans la transaction de retrait de membre.
    GameVisibility.objects.filter(owned_game__owner_id=user_id, community_id=community_id).delete()


def add_to_collection(
    user: User,
    game_id: UUID | None,
    title: str,
    notes: str,
    community_ids: list[UUID],
    proposal_reason: str = "",
) -> OwnedGame:
    from muqola.catalogue.services import write_game

    with domain_write(user):
        if game_id is None:
            game_id = write_game(user, {"title": title, "proposal_reason": proposal_reason}).pk
        return write_copy(user, game_id, notes, community_ids)


def archive(user: User, copy_id: UUID) -> None:
    with domain_write(user):
        item = get_object_or_404(
            OwnedGame.objects.select_for_update(), pk=copy_id, owner=user, archived=False
        )
        if item.loans.filter(state__in=["ACCEPTED", "HANDED_OVER"]).exists():
            raise ValidationError("Clôturez le prêt actif avant d'archiver cet exemplaire.")
        item.archived = True
        item.save()
        item.visibilities.all().delete()
        from muqola.loans.services import close_ineligible_requests

        close_ineligible_requests(user, copy_id=item.pk)
