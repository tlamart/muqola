import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.http import Http404
from django.test import Client
from django.urls import reverse

from muqola.catalogue import moderation
from muqola.catalogue.models import (
    Game,
    GameAlias,
    GameDecision,
    GameExternalIdentifier,
    GameIllustration,
    GameMerge,
    GameReport,
)
from muqola.catalogue.services import report, search, write_game
from muqola.catalogue.wikidata_importer import illustration
from muqola.communities import services as communities
from muqola.communities.models import Membership
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import add_to_collection, visible, write_copy
from muqola.loans import services as loans
from muqola.loans.models import Loan
from muqola.operations.models import OperatorAction
from tests.helpers import approved_game, catalogue_operator, member
from tests.test_wikidata_import import picture

pytestmark = pytest.mark.django_db


def approve(game: Game, **metadata: Any) -> Game:
    return moderation.decide(
        catalogue_operator(),
        game.pk,
        Game.Status.APPROVED,
        "Revue administrative",
        {"kind": "standalone", **metadata},
    )


def test_title_only_proposal_is_private_and_cannot_be_published_by_form_or_direct_post(
    client: Client,
) -> None:
    alice, bob = member(), member("Bob")
    client.force_login(alice)
    response = client.post(
        reverse("catalogue:create"), {"title": "Titre uniquement", "moderation_status": "approved"}
    )
    assert response.status_code == 302
    game = Game.objects.get()
    assert game.moderation_status == Game.Status.PENDING and game.kind == Game.Kind.UNKNOWN
    assert not search(alice).exists() and not search(bob).exists()
    copy = write_copy(alice, game.pk, "Note privée", [])
    assert copy.available  # private availability does not grant a third-party right
    community = communities.create(alice, "Privée")
    Membership.objects.create(user=bob, community=community)
    with pytest.raises(Http404):
        write_copy(bob, game.pk, "", [])
    client.force_login(bob)
    for name, args in [
        ("catalogue:detail", [game.pk]),
        ("catalogue:edit", [game.pk]),
        ("catalogue:add-copy", [game.pk]),
        ("inventory:detail", [copy.pk]),
    ]:
        assert client.get(reverse(name, args=args)).status_code == 404
    assert game.title not in client.get(reverse("catalogue:proposals")).content.decode()
    write_copy(alice, game.pk, "", [community.pk], copy_id=copy.pk)
    assert visible(bob).get() == copy
    assert client.get(reverse("catalogue:detail", args=[game.pk])).status_code == 200
    assert not search(bob).exists()  # shared pending is still outside the global catalogue
    loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    assert not GameIllustration.objects.exists()


def test_author_tracks_changes_rejection_resubmission_and_validation(client: Client) -> None:
    owner = member()
    game = write_game(owner, {"title": "Proposition"})
    operator = catalogue_operator()
    moderation.decide(operator, game.pk, Game.Status.PENDING, "Précisez le titre")
    client.force_login(owner)
    assert (
        "Précisez le titre"
        in client.get(reverse("catalogue:detail", args=[game.pk])).content.decode()
    )
    moderation.decide(operator, game.pk, Game.Status.REJECTED, "Titre à corriger")
    write_game(owner, {"title": "Titre corrigé"}, game.pk)
    assert Game.objects.get(pk=game.pk).moderation_status == Game.Status.REJECTED
    with pytest.raises(ValidationError):
        moderation.decide(operator, game.pk, Game.Status.APPROVED, "Type manquant")
    game.refresh_from_db()
    assert game.moderation_status == Game.Status.REJECTED
    approve(game)
    with pytest.raises(ValidationError):
        write_game(owner, {"title": "Modification non autorisée"}, game.pk)
    assert GameDecision.objects.filter(game=game).count() == 3


@pytest.mark.parametrize("kind", [Game.Kind.STANDALONE, Game.Kind.STANDALONE_EXPANSION])
def test_approval_requires_only_title_and_known_kind(kind: str) -> None:
    game = write_game(member(), {"title": "Jeu minimal"})
    approve(game, kind=kind)
    game.refresh_from_db()
    assert game.base_game_id is None and game.moderation_status == Game.Status.APPROVED
    assert game.publisher == game.description == "" and game.year is None


def test_extensions_require_one_approved_base_and_cannot_form_cycles() -> None:
    owner = member()
    base = approved_game(owner, {"title": "Base"})
    expansion = write_game(owner, {"title": "Extension", "kind": Game.Kind.EXPANSION})
    with pytest.raises(ValidationError):
        approve(expansion, kind=Game.Kind.EXPANSION)
    approve(expansion, kind=Game.Kind.EXPANSION, base_game_id=base.pk)
    with pytest.raises(ValidationError):
        moderation.correct(
            catalogue_operator(),
            base.pk,
            "Cycle interdit",
            {"kind": Game.Kind.EXPANSION, "base_game_id": expansion.pk},
        )
    with pytest.raises(ValidationError):
        write_game(
            owner,
            {"title": "Auto", "kind": Game.Kind.EXPANSION, "base_game_id": expansion.pk},
            expansion.pk,
        )
    assert Game.objects.get(pk=base.pk).base_game_id is None


def test_database_constraints_reject_unknown_approved_kind_and_missing_base() -> None:
    game = write_game(member(), {"title": "Test"})
    cases: list[dict[str, Any]] = [
        {"moderation_status": "invalid"},
        {"moderation_status": "approved"},
        {"moderation_status": "approved", "kind": "expansion"},
        {"base_game_id": game.pk},
        {"merged_into_id": game.pk},
    ]
    for fields in cases:
        with pytest.raises(IntegrityError), transaction.atomic():
            Game.objects.filter(pk=game.pk).update(**fields)


def test_alias_suggestions_and_duplicate_guards_cover_old_form_and_approval(client: Client) -> None:
    alice, bob = member(), member("Bob")
    existing = approved_game(alice, {"title": "Titre français", "aliases": ["Équivalent anglais"]})
    client.force_login(bob)
    response = client.get(
        reverse("catalogue:index"), {"manual": "1", "title": "EQUIVALENT ANGLAIS"}
    )
    assert existing.title in response.content.decode()
    for route in ("catalogue:index", "catalogue:create"):
        assert (
            client.post(
                reverse(route), {"title": "EQUIVALENT ANGLAIS", "distinct_edition": "on"}
            ).status_code
            == 400
        )
    with pytest.raises(ValidationError):
        write_game(bob, {"title": "Autre titre", "aliases": ["Équivalent anglais"]})
    assert Game.objects.count() == 1
    proposal = write_game(
        bob, {"title": "Équivalent anglais", "proposal_reason": "Homonyme réellement différent"}
    )
    with pytest.raises(ValidationError, match="Doublon"):
        approve(proposal)
    moderation.decide(
        catalogue_operator(),
        proposal.pk,
        Game.Status.APPROVED,
        "Homonymie examinée",
        {"kind": "standalone"},
        "Deux jeux distincts, pas deux éditions",
    )
    assert search(bob, "equivalent anglais").count() == 2


def test_legacy_rights_continue_without_catalogue_reuse(client: Client) -> None:
    alice, bob = member(), member("Bob")
    community = communities.create(alice, "Ancienne")
    Membership.objects.create(community=community, user=bob)
    game = Game.objects.create(
        title="Héritage", created_by=alice, moderation_status=Game.Status.LEGACY
    )
    copy = OwnedGame.objects.create(game=game, owner=alice)
    GameVisibility.objects.create(owned_game=copy, community=community)
    assert not search(bob).exists() and visible(bob).get() == copy
    client.force_login(bob)
    assert client.get(reverse("catalogue:detail", args=[game.pk])).status_code == 200
    with pytest.raises(Http404):
        add_to_collection(bob, game.pk, "", "", [])
    loan = loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7))
    loans.transition(alice, loan.pk, "accept")
    communities.remove(bob, community.pk, bob.pk)
    loans.transition(alice, loan.pk, "handover")
    loans.transition(alice, loan.pk, "return")
    assert Loan.objects.get(pk=loan.pk).state == Loan.State.RETURNED


def test_operator_only_decisions_and_cli_read_only_inventory() -> None:
    owner = member()
    game = write_game(owner, {"title": "Privée"})
    for user in (owner, member("Unverified", verified=False)):
        with pytest.raises(PermissionDenied):
            moderation.decide(
                user, game.pk, Game.Status.APPROVED, "Tentative", {"kind": "standalone"}
            )
    community = communities.create(owner, "Administrateur local")
    assert communities.membership(owner, community.pk).role == "admin"
    with pytest.raises(PermissionDenied):
        moderation.merge(owner, game.pk, game.pk, "Tentative")
    output = StringIO()
    call_command("ops", "catalogue-review", operator=catalogue_operator().email, stdout=output)
    assert json.loads(output.getvalue())[0]["title"] == game.title
    output = StringIO()
    call_command("ops", "catalogue-inventory", operator=catalogue_operator().email, stdout=output)
    assert owner.email not in output.getvalue() and game.title not in output.getvalue()
    assert "references" in output.getvalue()
    target = approved_game(owner, {"title": "Cible CLI"})
    output = StringIO()
    call_command(
        "ops",
        "merge-games",
        operator=catalogue_operator().email,
        game_id=game.pk,
        target_game_id=target.pk,
        reason="Simulation CLI",
        dry_run=True,
        stdout=output,
    )
    assert json.loads(output.getvalue())["dry_run"] and not GameMerge.objects.exists()
    output = StringIO()
    call_command(
        "ops",
        "merge-games",
        operator=catalogue_operator().email,
        game_id=game.pk,
        target_game_id=target.pk,
        reason="Fusion CLI",
        apply=True,
        stdout=output,
    )
    assert not json.loads(output.getvalue())["dry_run"]
    assert Game.objects.get(pk=game.pk).merged_into_id == target.pk


def test_merge_preserves_every_copy_loan_report_alias_identifier_and_illustration(
    client: Client,
) -> None:
    alice, bob = member(), member("Bob")
    source = approved_game(
        alice,
        {
            "title": "Source",
            "aliases": ["Alias partagé", "Alias source"],
            "external_ids": [{"source": "synthetic", "identifier": "s"}],
        },
    )
    target = approved_game(
        bob,
        {
            "title": "Cible",
            "aliases": ["Alias partagé"],
            "external_ids": [{"source": "synthetic", "identifier": "t"}],
        },
    )
    for game in (source, target):
        illustration(picture(), game).save()
        report(alice, game.pk, "Signalement à conserver " + game.title)
    community = communities.create(alice, "Partagée")
    Membership.objects.create(community=community, user=bob)
    copies = [write_copy(alice, source.pk, "Privé", [])]
    states = {}
    for state in Loan.State.values:
        copy = write_copy(alice, source.pk, "Boîte", [community.pk])
        copies.append(copy)
        loan = Loan.objects.create(
            owned_game=copy,
            owner=alice,
            borrower=bob,
            state=state,
            due_date=loans.today() + timedelta(days=7),
        )
        states[loan.pk] = (loan.owned_game_id, loan.owner_id, loan.borrower_id, loan.state)
    ids = {
        model: set(model.objects.values_list("pk", flat=True))
        for model in (
            Game,
            OwnedGame,
            Loan,
            GameReport,
            GameAlias,
            GameExternalIdentifier,
            GameIllustration,
        )
    }
    visibility_ids = set(GameVisibility.objects.values_list("pk", flat=True))
    before_audit = OperatorAction.objects.count()
    preview = moderation.merge(catalogue_operator(), source.pk, target.pk, "Fusion simulée")
    assert preview["dry_run"] and OperatorAction.objects.count() == before_audit
    assert Game.objects.get(pk=source.pk).merged_into_id is None
    moderation.merge(catalogue_operator(), source.pk, target.pk, "Même jeu vérifié", dry_run=False)
    for model, previous in ids.items():
        assert previous <= set(model.objects.values_list("pk", flat=True))
    assert set(GameVisibility.objects.values_list("pk", flat=True)) == visibility_ids
    assert OwnedGame.objects.filter(
        pk__in=[copy.pk for copy in copies], game=target, owner=alice
    ).count() == len(copies)
    assert GameReport.objects.filter(game=target, resolved_at__isnull=True).count() == 2
    assert GameReport.objects.values("original_game").distinct().count() == 2
    assert set(
        GameExternalIdentifier.objects.filter(game=target).values_list("identifier", flat=True)
    ) == {"s", "t"}
    assert {
        loan.pk: (loan.owned_game_id, loan.owner_id, loan.borrower_id, loan.state)
        for loan in Loan.objects.all()
    } == states
    assert Game.objects.get(pk=target.pk).ever_reused
    client.force_login(alice)
    response = client.get(reverse("catalogue:detail", args=[source.pk]))
    assert response.status_code == 302 and str(target.pk) in response["Location"]
    assert "Illustration conservée" in client.get(response["Location"]).content.decode()
    assert GameMerge.objects.get().references["copies"]
    accepted = Loan.objects.get(state=Loan.State.ACCEPTED)
    loans.transition(alice, accepted.pk, "handover")
    loans.transition(alice, accepted.pk, "return")


def test_merge_refuses_unmasking_cycles_and_rolls_back_failures() -> None:
    owner = member()
    source = approved_game(owner, {"title": "Base source"})
    target = approved_game(owner, {"title": "Cible"})
    target.hidden = True
    target.save()
    with pytest.raises(ValidationError, match="masquages"):
        moderation.merge(catalogue_operator(), source.pk, target.pk, "Refus", dry_run=False)
    target.hidden = False
    target.save()
    moderation.correct(
        catalogue_operator(),
        target.pk,
        "Extension",
        {"kind": "expansion", "base_game_id": source.pk},
    )
    with pytest.raises(ValidationError, match="cycle"):
        moderation.merge(catalogue_operator(), source.pk, target.pk, "Refus")
    moderation.correct(
        catalogue_operator(), target.pk, "Autonome", {"kind": "standalone", "base_game_id": None}
    )
    copy = write_copy(owner, source.pk, "", [])
    with (
        patch.object(GameMerge.objects, "create", side_effect=RuntimeError("panne")),
        pytest.raises(RuntimeError),
    ):
        moderation.merge(catalogue_operator(), source.pk, target.pk, "Rollback", dry_run=False)
    copy.refresh_from_db()
    assert copy.game_id == source.pk and not GameMerge.objects.exists()
    assert not Game.objects.filter(pk=source.pk, merged_into__isnull=False).exists()


def race(*actions: Callable[[], Any]) -> list[bool]:
    barrier = Barrier(len(actions))

    def execute(action: Callable[[], Any]) -> bool:
        try:
            barrier.wait(timeout=10)
            action()
            return True
        except (ValidationError, Http404):
            return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(execute, actions))


@pytest.mark.django_db(transaction=True)
def test_concurrent_proposals_and_approvals_do_not_publish_duplicate_games() -> None:
    alice, bob = member(), member("Bob")
    assert (
        sum(
            race(
                lambda: write_game(alice, {"title": "Identique"}),
                lambda: write_game(alice, {"title": "IDENTIQUE"}),
            )
        )
        == 1
    )
    first = Game.objects.get(created_by=alice)
    second = write_game(bob, {"title": "Identique"})
    catalogue_operator()
    assert sum(race(lambda: approve(first), lambda: approve(second))) == 1
    assert Game.objects.filter(moderation_status=Game.Status.APPROVED).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("other", ["add_copy", "request_loan", "correct", "approve"])
def test_merge_races_with_addition_lending_and_correction(other: str) -> None:
    alice, bob = member(), member("Bob")
    source = approved_game(alice, {"title": "Source"})
    target = approved_game(alice, {"title": "Cible"})
    community = communities.create(alice, "A")
    Membership.objects.create(user=bob, community=community)
    copy = write_copy(alice, source.pk, "", [community.pk])
    actions = {
        "add_copy": lambda: write_copy(bob, source.pk, "", []),
        "request_loan": lambda: loans.request_loan(bob, copy.pk, loans.today() + timedelta(days=7)),
        "approve": lambda: approve(source),
        "correct": lambda: moderation.correct(
            catalogue_operator(), source.pk, "Correction simultanée", {"description": "Description"}
        ),
    }
    result = race(
        lambda: moderation.merge(
            catalogue_operator(), source.pk, target.pk, "Fusion", dry_run=False
        ),
        actions[other],
    )
    assert result[0]
    copy.refresh_from_db()
    assert copy.game_id == target.pk and Game.objects.get(pk=source.pk).merged_into_id == target.pk
    assert not OwnedGame.objects.filter(game=source).exists()
    assert all(loan.owned_game_id == copy.pk for loan in Loan.objects.all())


def test_pending_merge_keeps_private_copy_and_old_url_authorization(client: Client) -> None:
    alice, bob = member(), member("Bob")
    pending = write_game(alice, {"title": "Proposition privée"})
    copy = write_copy(alice, pending.pk, "Note confidentielle", [])
    target = approved_game(bob, {"title": "Fiche canonique"})
    moderation.merge(catalogue_operator(), pending.pk, target.pk, "Doublon vérifié", dry_run=False)
    copy.refresh_from_db()
    assert (
        copy.game_id == target.pk
        and copy.owner_id == alice.pk
        and copy.notes == "Note confidentielle"
    )
    assert not copy.visibilities.exists() and not visible(bob).filter(pk=copy.pk).exists()
    client.force_login(bob)
    assert client.get(reverse("catalogue:detail", args=[pending.pk])).status_code == 404
    client.force_login(alice)
    assert client.get(reverse("catalogue:detail", args=[pending.pk])).status_code == 302


def test_invalid_admin_metadata_rolls_back_status_aliases_and_audit() -> None:
    owner = member()
    approved_game(
        owner,
        {"title": "Existante", "external_ids": [{"source": "synthetic", "identifier": "unique"}]},
    )
    game = write_game(owner, {"title": "Nouvelle proposition"})
    audits = OperatorAction.objects.count()
    with pytest.raises(ValidationError):
        approve(
            game,
            aliases=["Alias temporaire"],
            external_ids=[{"source": "synthetic", "identifier": "unique"}],
        )
    assert Game.objects.get(pk=game.pk).moderation_status == Game.Status.PENDING
    assert not game.aliases.exists() and OperatorAction.objects.count() == audits
    with pytest.raises(ValidationError):
        moderation.correct(catalogue_operator(), game.pk, "Erreur de type JSON", {"title": None})
    assert Game.objects.get(pk=game.pk).title == "Nouvelle proposition"


def test_operator_correction_resolves_reports_without_erasing_them() -> None:
    owner = member()
    game = approved_game(owner, {"title": "À corriger"})
    report(owner, game.pk, "Description à revoir")
    entry = GameReport.objects.get()
    moderation.correct(
        catalogue_operator(),
        game.pk,
        "Correction vérifiée",
        {"description": "Description corrigée"},
    )
    entry.refresh_from_db()
    assert entry.resolved_at is not None and entry.reason == "Description à revoir"
    assert entry.original_game_id == game.pk and GameReport.objects.count() == 1


@pytest.mark.parametrize("route", ["catalogue:create", "catalogue:index"])
def test_uploaded_photo_is_explicitly_rejected_without_any_persistence(
    client: Client, route: str
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(member())
    response = client.post(
        reverse(route),
        {
            "title": "Proposition sans photo",
            "image": SimpleUploadedFile("photo.png", b"synthetic", content_type="image/png"),
        },
    )
    assert response.status_code == 400
    assert "photos utilisateur ne sont pas acceptés" in response.content.decode()
    assert (
        not Game.objects.exists()
        and not OwnedGame.objects.exists()
        and not GameIllustration.objects.exists()
    )


def test_extension_form_names_approved_bases_without_revealing_private_proposals(
    client: Client,
) -> None:
    alice, bob = member(), member("Bob")
    base = approved_game(alice, {"title": "Base nommée et validée"})
    private = write_game(alice, {"title": "Proposition strictement privée"})
    client.force_login(bob)
    response = client.get(reverse("catalogue:create"))
    assert response.status_code == 200
    assert f'value="{base.pk}">{base.title}</option>' in response.content.decode()
    assert (
        private.title not in response.content.decode()
        and str(private.pk) not in response.content.decode()
    )
