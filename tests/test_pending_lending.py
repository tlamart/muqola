"""Pending metadata is scoped by copies; moderation never erases physical loans."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import Client
from django.urls import reverse

from muqola.catalogue import moderation
from muqola.catalogue.models import Game, GameAlias
from muqola.catalogue.services import search, write_game
from muqola.communities import services as communities
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import available, borrowable, visible, write_copy
from muqola.loans import services as loans
from muqola.loans.models import Loan
from tests.helpers import approved_game, catalogue_operator, member
from tests.test_catalogue_refonte import race

pytestmark = pytest.mark.django_db


def scenario() -> tuple[User, User, User, Community, OwnedGame]:
    owner, reader, outsider = member(), member("Reader"), member("Outsider")
    a = communities.create(owner, "Autorisée A")
    b = communities.create(outsider, "Étrangère B")
    Membership.objects.create(user=reader, community=a)
    Membership.objects.create(user=owner, community=b)
    game = write_game(
        owner, {"title": "Constellation fictive", "proposal_reason": "Motif privé auteur"}
    )
    GameAlias.objects.create(game=game, title="Étoiles fictives")
    item = write_copy(owner, game.pk, "Boîte partagée A", [a.pk])
    return owner, reader, outsider, a, item


def test_manual_quick_add_shares_pending_without_operator_or_javascript(client: Client) -> None:
    owner, reader, outsider, a, _ = scenario()
    client.force_login(owner)
    response = client.get(reverse("catalogue:index"), {"manual": "1"})
    assert b"hidden disabled" not in response.content
    response = client.post(
        reverse("catalogue:index"),
        {
            "title": "Nouvelle proposition partagée",
            "communities": [str(a.pk)],
            "notes": "Boîte neuve",
            "moderation_status": "approved",
        },
    )
    assert response.status_code == 302
    item = OwnedGame.objects.get(game__title="Nouvelle proposition partagée")
    assert (
        item.game.moderation_status == Game.Status.PENDING and item.game.kind == Game.Kind.UNKNOWN
    )
    assert item.visibilities.get().community_id == a.pk
    assert visible(reader).filter(pk=item.pk).exists()
    assert not visible(outsider).exists()
    assert not search(reader, item.game.title).exists()


def test_pending_scope_search_detail_aliases_and_private_moderation_fields(client: Client) -> None:
    owner, reader, outsider, a, item = scenario()
    other = communities.create(owner, "Autorisée C")
    Membership.objects.create(user=reader, community=other)
    write_copy(owner, item.game_id, item.notes, [a.pk, other.pk], copy_id=item.pk)
    private = write_copy(owner, item.game_id, "Notes privées jamais partagées", [])
    moderation.decide(
        catalogue_operator(), item.game_id, Game.Status.PENDING, "Motif privé opérateur"
    )
    client.force_login(reader)
    for headers in ("", "live-search"):
        response = client.get(
            reverse("inventory:index"),
            {"title": "ETOILES fictives", "community": str(a.pk)},
            HTTP_X_REQUESTED_WITH=headers,
        )
        found = response.context["games"]
        assert found.paginator.count == 1
        assert found[0].pk == item.game_id and found[0].copy_count == found[0].available_count == 1
        assert "Fiche en attente de validation" in response.content.decode()
        assert (
            client.get(
                reverse("catalogue:index"),
                {"title": "ETOILES fictives"},
                HTTP_X_REQUESTED_WITH=headers,
            )
            .context["games"]
            .paginator.count
            == 0
        )
    for name in ("catalogue:detail", "inventory:game"):
        response = client.get(reverse(name, args=[item.game_id]))
        assert response.status_code == 200
        body = response.content.decode()
        assert "Fiche en attente de validation" in body
        assert "Motif privé" not in body and "Notes privées" not in body and owner.email not in body
        assert all(row["copy"].pk == item.pk for row in response.context["copy_rows"])
    assert client.get(reverse("inventory:detail", args=[private.pk])).status_code == 404
    # Seeing a shared proposal is not permission to edit or reuse it globally.
    for name in ("catalogue:edit", "catalogue:add-copy"):
        assert client.get(reverse(name, args=[item.game_id])).status_code == 404
    with pytest.raises(Http404):
        write_copy(reader, item.game_id, "", [])
    client.force_login(outsider)
    for name, pk in (
        ("catalogue:detail", item.game_id),
        ("inventory:game", item.game_id),
        ("inventory:detail", item.pk),
        ("inventory:request", item.pk),
    ):
        assert client.get(reverse(name, args=[pk])).status_code == 404
    assert (
        client.get(
            reverse("inventory:index"), {"title": "etoiles"}, HTTP_X_REQUESTED_WITH="live-search"
        )
        .context["games"]
        .paginator.count
        == 0
    )
    assert not search(owner).exists() and not search(outsider).exists()


@pytest.mark.parametrize(
    "restriction",
    [
        "private",
        "withdrawn",
        "archived",
        "hidden",
        "owner_left",
        "reader_left",
        "inactive_owner",
        "unverified_owner",
    ],
)
def test_pending_permissions_are_the_same_as_validated_copies(
    restriction: str, client: Client
) -> None:
    owner, reader, _, a, item = scenario()
    if restriction == "private":
        write_copy(owner, item.game_id, "", [], copy_id=item.pk)
    elif restriction in ("withdrawn", "archived"):
        setattr(item, restriction, True)
        item.save()
    elif restriction == "hidden":
        Game.objects.filter(pk=item.game_id).update(hidden=True)
    elif restriction in ("owner_left", "reader_left"):
        Membership.objects.filter(
            community=a, user=owner if restriction == "owner_left" else reader
        ).update(active=False)
    else:
        if restriction == "inactive_owner":
            owner.is_active = False
        else:
            owner.email_verified_at = None
        owner.save()
    assert not borrowable(reader).exists()
    with pytest.raises(Http404):
        loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
    client.force_login(reader)
    assert client.get(reverse("catalogue:detail", args=[item.game_id])).status_code == 404
    assert client.get(reverse("inventory:game", args=[item.game_id])).status_code == 404


def test_pending_full_http_loan_cycle_and_actor_checks(client: Client) -> None:
    owner, reader, outsider, _, item = scenario()
    assert item.available and available(borrowable(reader)).get().pk == item.pk
    with pytest.raises(ValidationError):
        loans.request_loan(owner, item.pk, loans.today() + timedelta(days=7))
    client.force_login(reader)
    response = client.post(
        reverse("inventory:request", args=[item.pk]),
        {"due_date": loans.today() + timedelta(days=7)},
    )
    assert response.status_code == 302
    loan = Loan.objects.get()
    with pytest.raises(PermissionDenied):
        loans.transition(reader, loan.pk, "accept")
    client.force_login(outsider)
    assert client.post(reverse("loans:action", args=[loan.pk, "accept"])).status_code == 404
    client.force_login(owner)
    assert client.post(reverse("loans:action", args=[loan.pk, "accept"])).status_code == 302
    assert loans.contacts(reader, loan.pk) == {"owner": owner.email, "borrower": reader.email}
    assert (
        "Fiche en attente de validation"
        in client.get(reverse("loans:detail", args=[loan.pk])).content.decode()
    )
    for action in ("handover", "return"):
        assert client.post(reverse("loans:action", args=[loan.pk, action])).status_code == 302
    loan.refresh_from_db()
    assert loan.state == Loan.State.RETURNED and loans.contacts(reader, loan.pk) is None


@pytest.mark.parametrize("decision", ["approve", "correct", "merge", "reject"])
def test_moderation_preserves_copies_shares_and_every_loan_state(decision: str) -> None:
    owner, reader, outsider, a, first = scenario()
    entries = []
    for state in Loan.State.values:
        item = write_copy(owner, first.game_id, state, [a.pk])
        entries.append(
            Loan.objects.create(
                owned_game=item,
                owner=owner,
                borrower=reader,
                state=state,
                due_date=loans.today() + timedelta(days=7),
            )
        )
    snapshots = list(OwnedGame.objects.order_by("pk").values())
    shares = list(GameVisibility.objects.order_by("pk").values())
    operator = catalogue_operator()
    target_id = first.game_id
    if decision == "approve":
        moderation.decide(
            operator, first.game_id, Game.Status.APPROVED, "Validé", {"kind": "standalone"}
        )
    elif decision == "correct":
        moderation.correct(
            operator, first.game_id, "Correction", {"title": "Constellation corrigée"}
        )
    elif decision == "merge":
        target_id = approved_game(owner, {"title": "Fiche canonique"}).pk
        moderation.merge(operator, first.game_id, target_id, "Doublon fusionné", dry_run=False)
    else:
        moderation.decide(operator, first.game_id, Game.Status.REJECTED, "Rejet motivé")
    assert list(GameVisibility.objects.order_by("pk").values()) == shares
    for row in snapshots:
        row["game_id"] = target_id
    assert list(OwnedGame.objects.order_by("pk").values()) == snapshots
    assert Loan.objects.count() == len(entries)
    for entry in entries:
        previous = entry.state
        entry.refresh_from_db()
        assert entry.owned_game_id and entry.owner_id == owner.pk and entry.borrower_id == reader.pk
        assert entry.state == (
            Loan.State.CANCELLED
            if decision == "reject" and previous == Loan.State.REQUESTED
            else previous
        )
        if previous == Loan.State.ACCEPTED:
            loans.transition(owner, entry.pk, "handover")
            loans.transition(owner, entry.pk, "return")
        elif previous == Loan.State.HANDED_OVER:
            loans.transition(owner, entry.pk, "return")
        with pytest.raises(Http404):
            loans.contacts(outsider, entry.pk)
    if decision == "reject":
        assert not borrowable(reader).exists()
        with pytest.raises(Http404):
            loans.request_loan(reader, first.pk, loans.today() + timedelta(days=7))


def test_rejection_cannot_be_lifted_by_author_edit_and_existing_shares_are_retained() -> None:
    owner, reader, _, a, item = scenario()
    rejected = moderation.decide(catalogue_operator(), item.game_id, Game.Status.REJECTED, "Rejet")
    saved = write_game(owner, {"title": "Correction auteur"}, rejected.pk)
    assert saved.moderation_status == Game.Status.REJECTED
    write_copy(owner, saved.pk, "Notes corrigées", [a.pk], copy_id=item.pk)
    assert item.visibilities.count() == 1 and not borrowable(reader).exists()
    extra = communities.create(owner, "Nouveau partage")
    with pytest.raises(ValidationError):
        write_copy(owner, saved.pk, "", [a.pk, extra.pk], copy_id=item.pk)
    moderation.decide(catalogue_operator(), saved.pk, Game.Status.PENDING, "Réexamen autorisé")
    assert borrowable(reader).get().pk == item.pk
    assert not search(reader).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["request", "accept"])
def test_rejection_races_never_leave_an_eligible_pending_request(operation: str) -> None:
    owner, reader, _, _, item = scenario()
    operator = catalogue_operator()
    loan = (
        loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
        if operation == "accept"
        else None
    )

    def action() -> Loan:
        if operation == "accept":
            assert loan is not None
            return loans.transition(owner, loan.pk, "accept")
        return loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))

    result = race(
        lambda: moderation.decide(operator, item.game_id, Game.Status.REJECTED, "Rejet concurrent"),
        action,
    )
    assert result[0]
    assert not Loan.objects.filter(state=Loan.State.REQUESTED).exists()
    assert not borrowable(reader).exists()
    for active in Loan.objects.filter(state=Loan.State.ACCEPTED):
        loans.transition(owner, active.pk, "handover")
        loans.transition(owner, active.pk, "return")


@pytest.mark.django_db(transaction=True)
def test_pending_copies_keep_exclusive_acceptance() -> None:
    owner, reader, outsider, a, item = scenario()
    Membership.objects.create(user=outsider, community=a)
    first = loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
    second = loans.request_loan(outsider, item.pk, first.due_date)
    assert (
        sum(
            race(
                lambda: loans.transition(owner, first.pk, "accept"),
                lambda: loans.transition(owner, second.pk, "accept"),
            )
        )
        == 1
    )
    assert Loan.objects.filter(state=Loan.State.ACCEPTED).count() == 1
    assert Loan.objects.filter(state=Loan.State.CANCELLED).count() == 1


def test_invisible_pending_copies_leave_fragment_counts_order_and_pagination_unchanged(
    client: Client,
) -> None:
    owner, reader, outsider, _, item = scenario()
    client.force_login(reader)
    url = reverse("inventory:index")
    params = {"title": "constellation", "page": "1"}
    before = client.get(url, params, HTTP_X_REQUESTED_WITH="live-search").content
    write_copy(owner, item.game_id, "Collection strictement privée", [])
    foreign = Community.objects.get(name="Étrangère B")
    other = write_copy(owner, item.game_id, "Boîte visible seulement dans B", [foreign.pk])
    assert client.get(url, params, HTTP_X_REQUESTED_WITH="live-search").content == before
    assert not visible(reader).filter(pk=other.pk).exists()
    assert visible(outsider).get().pk == other.pk
    assert not search(outsider, "constellation").exists()


@pytest.mark.parametrize("state", [Loan.State.ACCEPTED, Loan.State.HANDED_OVER])
def test_rejected_active_loan_survives_loss_of_community(state: str, client: Client) -> None:
    owner, reader, outsider, a, item = scenario()
    loan = loans.request_loan(reader, item.pk, loans.today() + timedelta(days=7))
    loans.transition(owner, loan.pk, "accept")
    if state == Loan.State.HANDED_OVER:
        loans.transition(owner, loan.pk, "handover")
    moderation.decide(catalogue_operator(), item.game_id, Game.Status.REJECTED, "Rejet")
    communities.remove(owner, a.pk, reader.pk)
    assert not visible(reader).exists()
    client.force_login(reader)
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 200
    client.force_login(outsider)
    assert client.get(reverse("loans:detail", args=[loan.pk])).status_code == 404
    if state == Loan.State.ACCEPTED:
        loans.transition(owner, loan.pk, "handover")
    loans.transition(owner, loan.pk, "return")
    loan.refresh_from_db()
    assert loan.state == Loan.State.RETURNED and loans.contacts(reader, loan.pk) is None
