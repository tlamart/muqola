"""PostgreSQL ranking on a caller-authorized set of canonical games.

No frequency, copy count or corpus statistic participates in the score. Aliases
are correlated subqueries, never joins multiplying games or pagination rows.
"""

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import (
    Case,
    Exists,
    F,
    FloatField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Greatest

from muqola.catalogue.models import Game, GameAlias, normalized_title


def title_condition(title: str, *, exact: bool = False) -> Q:
    key = normalized_title(title[:120])
    lookup = "title_key" if exact else "title_key__contains"
    aliases = GameAlias.objects.filter(game_id=OuterRef("pk"), **{lookup: key})
    return Q(**{lookup: key}) | Q(Exists(aliases))


def matching_title(query: QuerySet[Game], title: str, *, exact: bool = False) -> QuerySet[Game]:
    """The caller supplies an already authorized queryset."""
    return query.filter(title_condition(title, exact=exact)) if title or exact else query


def ranked(query: QuerySet[Game], title: str) -> QuerySet[Game]:
    key = normalized_title(title[:120])
    if not key:
        return query.order_by("title_key", "id")
    if len(key) < 2:
        return query.none()
    aliases = GameAlias.objects.filter(game_id=OuterRef("pk"))
    candidate = Q(title_key__startswith=key)
    if len(key) >= 3:
        candidate |= Q(title_key__contains=key)
    if len(key) >= 4:
        candidate |= Q(title_key__trigram_similar=key)
    # Intersect indexed candidate IDs with the authorized outer relation before
    # any ranking/counting. The union permits independent principal/alias GIN
    # scans without repeating the authorization query or multiplying game rows.
    candidate_ids = (
        Game.objects.filter(candidate)
        .order_by()
        .values("pk")
        .union(GameAlias.objects.filter(candidate).order_by().values("game_id"))
    )
    query = (
        query.filter(pk__in=candidate_ids)
        .alias(
            alias_exact=Exists(aliases.filter(title_key=key)),
            alias_prefix=Exists(aliases.filter(title_key__startswith=key)),
            alias_contains=Exists(aliases.filter(title_key__contains=key)),
            search_score=Greatest(
                TrigramSimilarity("title_key", key),
                Coalesce(
                    Subquery(
                        aliases.annotate(score=TrigramSimilarity("title_key", key))
                        .order_by("-score")
                        .values("score")[:1],
                    ),
                    Value(0.0),
                    output_field=FloatField(),
                ),
            ),
        )
        .alias(
            search_tier=Case(
                When(title_key=key, then=Value(0)),
                When(alias_exact=True, then=Value(1)),
                When(title_key__startswith=key, then=Value(2)),
                When(alias_prefix=True, then=Value(3)),
                When(title_key__contains=key, then=Value(4)),
                When(alias_contains=True, then=Value(5)),
                default=Value(6),
            )
        )
    )
    # A short two-character title uses exact/prefix only. Typo matches need at
    # least four characters; thresholds are explicit, independent of the corpus.
    threshold = 0.2 if len(key) == 4 else 0.3
    textual = Q(title_key__contains=key) | Q(alias_contains=True)
    return (
        query.filter(textual | Q(search_score__gte=threshold))
        .alias(
            fuzzy_order=Case(
                When(textual, then=Value(0.0)),
                default=F("search_score"),
                output_field=FloatField(),
            )
        )
        .order_by("search_tier", "-fuzzy_order", "title_key", "id")
    )
