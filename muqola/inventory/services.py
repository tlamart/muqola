from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q, QuerySet
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
    verified(user)
    return (
        with_availability(OwnedGame.objects.filter(archived=False))
        .filter(
            Q(owner=user)
            | Q(
                withdrawn=False,
                game__hidden=False,
                visibilities__community__memberships__user=user,
                visibilities__community__memberships__active=True,
            )
        )
        .select_related("game", "owner")
        .distinct()
    )


def available(query: QuerySet[OwnedGame]) -> QuerySet[OwnedGame]:
    return with_availability(query).filter(
        withdrawn=False, archived=False, game__hidden=False, has_active_loan=False
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
        game = get_object_or_404(Game, pk=game_id, hidden=False)
        item = (
            OwnedGame(game=game, owner=user)
            if copy_id is None
            else get_object_or_404(OwnedGame, pk=copy_id, owner=user, archived=False)
        )
        if item.game_id != game.pk:
            raise ValidationError("La fiche d'un exemplaire ne peut pas être remplacée.")
        allowed = set(
            Membership.objects.filter(user=user, active=True).values_list("community_id", flat=True)
        )
        if not set(community_ids) <= allowed:
            raise ValidationError("Choisissez uniquement vos communautés actuelles.")
        item.notes, item.withdrawn = notes.strip(), withdrawn
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
