"""Operator-only, serialized catalogue decisions and logical merges."""

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Count, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from muqola.catalogue.models import (
    Game,
    GameAlias,
    GameDecision,
    GameExternalIdentifier,
    GameIllustration,
    GameMerge,
    GameReport,
    normalized_title,
)
from muqola.catalogue.services import FIELDS
from muqola.core.transactions import domain_write
from muqola.identity.models import User
from muqola.inventory.models import OwnedGame
from muqola.operations.services import audit, operator


def add_aliases(game: Game, titles: list[str]) -> None:
    if (
        not isinstance(titles, list)
        or len(titles) > 20
        or any(not isinstance(t, str) for t in titles)
    ):
        raise ValidationError("Au plus 20 titres alternatifs sont acceptés.")
    for title in titles:
        title = title.strip()
        if not title:
            continue
        alias = GameAlias(game=game, title=title, title_key=normalized_title(title))
        if GameAlias.objects.filter(game=game, title_key=alias.title_key).exists():
            continue
        alias.full_clean()
        alias.save()


def similar(game: Game) -> QuerySet[Game]:
    """Operator suggestions use the same ranked engine; approval guards stay exact."""
    from muqola.catalogue.matching import ranked

    return ranked(
        Game.objects.filter(
            hidden=False,
            merged_into__isnull=True,
            moderation_status__in=[Game.Status.APPROVED, Game.Status.LEGACY],
        ).exclude(pk=game.pk),
        game.title,
    )


def duplicates(game: Game) -> QuerySet[Game]:
    keys = {game.title_key, *game.aliases.values_list("title_key", flat=True)}
    return (
        Game.objects.filter(merged_into__isnull=True)
        .filter(Q(title_key__in=keys) | Q(aliases__title_key__in=keys))
        .exclude(pk=game.pk)
        .distinct()
    )


def apply_metadata(game: Game, metadata: dict[str, Any]) -> None:
    if not set(metadata) <= FIELDS | {"aliases", "external_ids"}:
        raise ValidationError(
            "Métadonnées génériques seulement ; statut et image ne sont pas éditables ici."
        )
    for key in FIELDS:
        if key in metadata:
            value = metadata[key]
            setattr(game, key, value.strip() if isinstance(value, str) else value)
    if not isinstance(game.title, str):
        raise ValidationError("Le titre doit être du texte.")
    game.title_key = normalized_title(game.title)
    game.full_clean()
    game.save()
    add_aliases(game, metadata.get("aliases", []))
    entries = metadata.get("external_ids", [])
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValidationError("Liste bornée d'identifiants externes attendue.")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"source", "identifier"}:
            raise ValidationError("Chaque identifiant exige source et identifier.")
        if not all(isinstance(value, str) and value.strip() for value in entry.values()):
            raise ValidationError("Source et identifiant doivent être du texte non vide.")
        item = GameExternalIdentifier(
            game=game, **{key: value.strip() for key, value in entry.items()}
        )
        if GameExternalIdentifier.objects.filter(
            game=game, source=item.source, identifier=item.identifier
        ).exists():
            continue
        item.full_clean()
        item.save()


def decide(
    user: User,
    game_id: UUID,
    status: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
    homonym_reason: str = "",
) -> Game:
    with domain_write(user):
        operator(user)
        if status not in (Game.Status.APPROVED, Game.Status.REJECTED, Game.Status.PENDING):
            raise ValidationError("Décision inconnue.")
        if len(homonym_reason) > 500:
            raise ValidationError("Justification d'homonymie trop longue.")
        game = get_object_or_404(Game, pk=game_id, merged_into__isnull=True)
        if (
            game.moderation_status in (Game.Status.APPROVED, Game.Status.LEGACY)
            and status != Game.Status.APPROVED
        ):
            raise ValidationError(
                "Une fiche publiée/héritée se masque par la modération, sans casser ses prêts."
            )
        audit(user, "catalogue_decision", str(game.pk), reason)
        game.moderation_status = status
        apply_metadata(game, metadata or {})
        if (
            status == Game.Status.APPROVED
            and duplicates(game)
            .filter(moderation_status__in=[Game.Status.APPROVED, Game.Status.LEGACY])
            .exists()
            and not homonym_reason.strip()
        ):
            raise ValidationError(
                "Doublon titre/alias à examiner : fusionnez ou justifiez une "
                "homonymie réelle, pas une édition."
            )
        if status == Game.Status.REJECTED:
            from muqola.loans.services import close_ineligible_requests

            close_ineligible_requests(
                user,
                game_id=game.pk,
                reason="La fiche du jeu a été rejetée. Cette demande ne peut plus être acceptée.",
            )
        GameDecision.objects.create(
            game=game,
            actor=user,
            status=status,
            reason=reason.strip(),
            homonym_reason=homonym_reason.strip(),
        )
        return game


def correct(
    user: User, game_id: UUID, reason: str, metadata: dict[str, Any], homonym_reason: str = ""
) -> None:
    with domain_write(user):
        operator(user)
        if len(homonym_reason) > 500:
            raise ValidationError("Justification d'homonymie trop longue.")
        game = get_object_or_404(Game, pk=game_id, merged_into__isnull=True)
        audit(user, "correct_game", str(game.pk), reason)
        apply_metadata(game, metadata)
        if (
            duplicates(game)
            .filter(moderation_status__in=[Game.Status.APPROVED, Game.Status.LEGACY])
            .exists()
            and not homonym_reason.strip()
        ):
            raise ValidationError(
                "Doublon titre/alias : justification d'homonymie administrative requise."
            )
        GameReport.objects.filter(game=game, resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )
        GameDecision.objects.create(
            game=game,
            actor=user,
            status=game.moderation_status,
            reason=reason.strip(),
            homonym_reason=homonym_reason.strip(),
        )


def merge(
    user: User, source_id: UUID, target_id: UUID, reason: str, *, dry_run: bool = True
) -> dict[str, Any]:
    with domain_write(user):
        operator(user)
        if source_id == target_id:
            raise ValidationError("Source et cible doivent être distinctes.")
        source = get_object_or_404(Game, pk=source_id, merged_into__isnull=True)
        target = get_object_or_404(
            Game, pk=target_id, merged_into__isnull=True, moderation_status=Game.Status.APPROVED
        )
        if source.hidden != target.hidden:
            raise ValidationError(
                "Fusion refusée : les masquages sont différents. Aucun accès ne "
                "peut être rétabli implicitement."
            )
        if not reason.strip() or len(reason) > 500:
            raise ValidationError("Motif de 1 à 500 caractères obligatoire.")
        # Validate the entire prospective base graph before any write.
        graph = dict(
            Game.objects.filter(merged_into__isnull=True)
            .exclude(pk=source.pk)
            .values_list("pk", "base_game_id")
        )
        graph = {key: target.pk if value == source.pk else value for key, value in graph.items()}
        for start in graph:
            seen: set[UUID] = set()
            current: UUID | None = start
            while current is not None:
                if current in seen:
                    raise ValidationError("Cette fusion créerait un cycle de jeux de base.")
                seen.add(current)
                current = graph.get(current)
        copies = list(OwnedGame.objects.filter(game=source).values_list("pk", flat=True))
        reports = list(GameReport.objects.filter(game=source).values_list("pk", flat=True))
        aliases = list(source.aliases.values_list("pk", flat=True))
        externals = list(source.external_identifiers.values_list("pk", flat=True))
        bases = list(Game.objects.filter(base_game=source).values_list("pk", flat=True))
        images = list(GameIllustration.objects.filter(game=source).values_list("pk", flat=True))
        refs: dict[str, Any] = {
            "copies": [str(pk) for pk in copies],
            "reports": reports,
            "aliases": aliases,
            "external_ids": externals,
            "base_references": [str(pk) for pk in bases],
            "illustrations": images,
        }
        if dry_run:
            return {
                "dry_run": True,
                "source": str(source.pk),
                "target": str(target.pk),
                "references": refs,
            }
        audit(user, "merge_game", f"{source.pk}:{target.pk}", reason)
        add_aliases(target, [source.title])
        for alias in source.aliases.all():
            if not target.aliases.filter(title_key=alias.title_key).exists():
                alias.game = target
                alias.save(update_fields=["game"])
            # Colliding aliases stay on the retained source: no row is deleted.
        source.external_identifiers.update(game=target)
        OwnedGame.objects.filter(pk__in=copies).update(game=target)
        GameReport.objects.filter(pk__in=reports).update(game=target)
        Game.objects.filter(base_game=source).update(base_game=target)
        Game.objects.filter(merged_into=source).update(merged_into=target)
        if not GameIllustration.objects.filter(game=target).exists():
            GameIllustration.objects.filter(game=source).update(game=target)
        # If both have an image, retain both; canonical detail lists the source's credits too.
        target.ever_reused = (
            target.ever_reused
            or source.ever_reused
            or OwnedGame.objects.filter(game=target).exclude(owner_id=target.created_by_id).exists()
        )
        target.save(update_fields=["ever_reused", "updated_at"])
        source.merged_into = target
        source.save(update_fields=["merged_into", "updated_at"])
        GameMerge.objects.create(
            source=source, target=target, actor=user, reason=reason.strip(), references=refs
        )
        return {
            "dry_run": False,
            "source": str(source.pk),
            "target": str(target.pk),
            "references": refs,
        }


def inventory(user: User) -> dict[str, Any]:
    """Read-only aggregates and actual FKs, usable before or after migration B."""
    operator(user)
    from django.db import connection

    from muqola.loans.models import Loan

    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, Game._meta.db_table)
        }
        references = []
        for table in sorted(tables):
            for constraint in connection.introspection.get_constraints(cursor, table).values():
                foreign_key = constraint.get("foreign_key")
                if foreign_key and foreign_key[0] in {
                    Game._meta.db_table,
                    OwnedGame._meta.db_table,
                }:
                    references.append(
                        {"table": table, "columns": constraint["columns"], "target": foreign_key[0]}
                    )
    has_status = "moderation_status" in columns
    total = Game.objects.count()
    return {
        "schema": "refonte_b" if has_status else "before_refonte_b",
        "games": total,
        "copies": OwnedGame.objects.count(),
        "loan_states": list(Loan.objects.values("state").annotate(count=Count("pk"))),
        "statuses": list(Game.objects.values("moderation_status").annotate(count=Count("pk")))
        if has_status
        else [{"moderation_status": "not_recorded", "count": total}],
        "unknown_types": Game.objects.filter(kind=Game.Kind.UNKNOWN).count()
        if "kind" in columns
        else total,
        "duplicate_title_groups": Game.objects.values("title_key")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .count(),
        "aliases": GameAlias.objects.count() if GameAlias._meta.db_table in tables else 0,
        "illustrations": GameIllustration.objects.count()
        if GameIllustration._meta.db_table in tables
        else 0,
        "external_identifiers": GameExternalIdentifier.objects.count()
        if GameExternalIdentifier._meta.db_table in tables
        else 0,
        "references": references,
    }
