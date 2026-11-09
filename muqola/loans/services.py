from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from muqola.communities.models import Membership
from muqola.core.transactions import domain_write, verified
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from muqola.loans.models import Loan, LoanEvent

ACTIVE = [Loan.State.ACCEPTED, Loan.State.HANDED_OVER]


def today() -> date:
    return timezone.localdate(timezone=ZoneInfo("Europe/Paris"))


def participant_loans(user: User) -> QuerySet[Loan]:
    verified(user)
    return Loan.objects.filter(Q(owner=user) | Q(borrower=user)).select_related(
        "owned_game__game", "owner", "borrower"
    )


def eligible(borrower: User, item: OwnedGame) -> bool:
    if borrower.pk == item.owner_id or item.withdrawn or item.archived or item.game.hidden:
        return False
    if not User.objects.filter(
        pk=borrower.pk, is_active=True, email_verified_at__isnull=False
    ).exists():
        return False
    if not User.objects.filter(
        pk=item.owner_id, is_active=True, email_verified_at__isnull=False
    ).exists():
        return False
    owners_communities = Membership.objects.filter(user_id=item.owner_id, active=True).values(
        "community_id"
    )
    return item.visibilities.filter(
        community_id__in=owners_communities,
        community__memberships__user=borrower,
        community__memberships__active=True,
    ).exists()


def event(loan: Loan, user: User, administrative: bool = False) -> None:
    LoanEvent.objects.create(
        loan=loan,
        actor=user,
        state=loan.state,
        reason=loan.close_reason,
        administrative=administrative,
    )


def request_loan(user: User, copy_id: UUID, due_date: date, message: str = "") -> Loan:
    from muqola.inventory.services import visible

    with domain_write(user):
        get_object_or_404(visible(user), pk=copy_id)
        item = OwnedGame.objects.select_for_update().select_related("game").get(pk=copy_id)
        if due_date <= today():
            raise ValidationError("La date de retour doit être après aujourd'hui (Europe/Paris).")
        if not eligible(user, item) or item.loans.filter(state__in=ACTIVE).exists():
            raise ValidationError("Cet exemplaire n'est pas disponible pour une demande.")
        if item.loans.filter(borrower=user, state=Loan.State.REQUESTED).exists():
            raise ValidationError(
                "Vous avez déjà une demande en attente. Annulez-la avant d'en refaire une."
            )
        loan = Loan(
            owned_game=item,
            owner_id=item.owner_id,
            borrower=user,
            due_date=due_date,
            message=message.strip(),
        )
        loan.full_clean()
        loan.save()
        event(loan, user)
        return loan


def finish(
    loan: Loan, user: User, state: str, reason: str = "", administrative: bool = False
) -> None:
    loan.state, loan.close_reason = state, reason
    loan.closed_at = timezone.now()
    loan.save()
    event(loan, user, administrative)


def close_ineligible_requests(
    user: User, copy_id: UUID | None = None, participant_id: int | None = None
) -> None:
    # Appelé sous domain_write par tous les changements d'accès/disponibilité.
    query = Loan.objects.filter(state=Loan.State.REQUESTED).select_related(
        "borrower", "owned_game__game"
    )
    if copy_id is not None:
        query = query.filter(owned_game_id=copy_id)
    if participant_id is not None:
        query = query.filter(Q(owner_id=participant_id) | Q(borrower_id=participant_id))
    for loan in query:
        if not eligible(loan.borrower, loan.owned_game):
            finish(
                loan,
                user,
                Loan.State.CANCELLED,
                "Cette demande n'est plus éligible après un changement "
                "de partage ou d'appartenance.",
            )


def transition(user: User, loan_id: UUID, action: str) -> Loan:
    with domain_write(user):
        loan = get_object_or_404(
            participant_loans(user).select_for_update(of=("self",)), pk=loan_id
        )
        if action in {"accept", "decline", "handover", "return"} and loan.owner_id != user.pk:
            raise PermissionDenied
        expected = {
            "accept": [Loan.State.REQUESTED],
            "decline": [Loan.State.REQUESTED],
            "cancel": [Loan.State.REQUESTED, Loan.State.ACCEPTED],
            "handover": [Loan.State.ACCEPTED],
            "return": [Loan.State.HANDED_OVER],
        }
        if action not in expected or loan.state not in expected[action]:
            raise ValidationError(
                "Cette action n'est plus possible dans l'état actuel. Rechargez le prêt."
            )
        if action == "accept":
            item = (
                OwnedGame.objects.select_for_update()
                .select_related("game")
                .get(pk=loan.owned_game_id)
            )
            if loan.due_date <= today():
                raise ValidationError(
                    "La date demandée est passée. Annulez puis demandez une nouvelle date future."
                )
            if not eligible(loan.borrower, item) or item.loans.filter(state__in=ACTIVE).exists():
                raise ValidationError(
                    "Cette demande n'est plus éligible ou l'exemplaire est déjà attribué."
                )
            loan.state, loan.accepted_at = Loan.State.ACCEPTED, timezone.now()
            loan.save()
            event(loan, user)
            for other in item.loans.filter(state=Loan.State.REQUESTED).exclude(pk=loan.pk):
                finish(
                    other,
                    user,
                    Loan.State.CANCELLED,
                    "L'exemplaire a été attribué à une autre demande.",
                )
        elif action == "handover":
            loan.state, loan.handed_over_at = Loan.State.HANDED_OVER, timezone.now()
            loan.save()
            event(loan, user)
        else:
            target = {
                "decline": Loan.State.DECLINED,
                "cancel": Loan.State.CANCELLED,
                "return": Loan.State.RETURNED,
            }[action]
            finish(loan, user, target)
        return loan


def contacts(user: User, loan_id: UUID) -> dict[str, str] | None:
    loan = get_object_or_404(participant_loans(user), pk=loan_id)
    if not loan.active:
        return None
    return {"owner": loan.owner.email, "borrower": loan.borrower.email}


def resolve(user: User, loan_id: UUID, resolution: str, reason: str) -> None:
    with domain_write(user):
        if not User.objects.filter(pk=user.pk, is_superuser=True).exists():
            raise PermissionDenied
        loan = get_object_or_404(Loan, pk=loan_id)
        if not reason.strip() or len(reason) > 500:
            raise ValidationError("Un motif non sensible de 1 à 500 caractères est obligatoire.")
        expected = (
            Loan.State.RETURNED if loan.state == Loan.State.HANDED_OVER else Loan.State.CANCELLED
        )
        if loan.state not in [Loan.State.REQUESTED, *ACTIVE] or resolution != expected:
            raise ValidationError(
                "Résolution incompatible : retour après remise, annulation avant remise."
            )
        finish(loan, user, resolution, reason.strip(), administrative=True)
