"""Reproducible synthetic-only benchmark, rolled back in a dedicated database."""

import json
import math
import platform
import statistics
import time
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from muqola.catalogue.models import Game, GameAlias
from muqola.catalogue.services import search
from muqola.communities.models import Community, Membership
from muqola.identity.models import User
from muqola.inventory.models import GameVisibility, OwnedGame
from muqola.inventory.services import borrowable, grouped


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--games", type=int, default=10000)
        parser.add_argument("--samples", type=int, default=30)
        parser.add_argument("--p95-budget-ms", type=int, default=3000)

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.APP_ENV != "test" or not connection.settings_dict["NAME"].endswith(
            "_benchmark"
        ):
            raise CommandError("APP_ENV=test et base dédiée *_benchmark obligatoires.")
        volume, samples = options["games"], options["samples"]
        if not 100 <= options["p95_budget_ms"] <= 30000:
            raise CommandError("Budget p95 entre 100 et 30000 ms.")
        if not 100 <= volume <= 50000 or not 10 <= samples <= 100:
            raise CommandError("Bornes : 100–50000 fiches, 10–100 mesures.")
        if Game.objects.exists() or User.objects.exists():
            raise CommandError("Base dédiée vide requise, aucune donnée existante modifiée.")
        with transaction.atomic():
            owner, reader = User.objects.bulk_create(
                [
                    User(
                        email=f"benchmark-{i}@example.test",
                        display_name=f"Synthétique {i}",
                        password="!",  # noqa: S106 — unusable password, synthetic account
                        email_verified_at=timezone.now(),
                    )
                    for i in range(2)
                ]
            )
            community = Community.objects.create(name="Groupe synthétique", created_by=owner)
            Membership.objects.bulk_create(
                [Membership(user=user, community=community) for user in (owner, reader)]
            )
            games = Game.objects.bulk_create(
                [
                    Game(
                        id=UUID(int=i + 1),
                        title=f"Royaume synthétique {i:05}",
                        title_key=f"royaume synthetique {i:05}",
                        created_by=owner,
                        moderation_status=Game.Status.APPROVED,
                        kind=Game.Kind.STANDALONE,
                    )
                    for i in range(volume)
                ]
            )
            GameAlias.objects.bulk_create(
                [
                    GameAlias(
                        game=game,
                        title=f"Palais fictif {i:05} {j}",
                        title_key=f"palais fictif {i:05} {j}",
                    )
                    for i, game in enumerate(games)
                    for j in range(3)
                ]
            )
            copies = OwnedGame.objects.bulk_create(
                [
                    OwnedGame(game=game, owner=owner, withdrawn=j == 2, archived=j == 3)
                    for game in games
                    for j in range(4)
                ]
            )
            # One authorized, one private, one withdrawn, one archived per game.
            GameVisibility.objects.bulk_create(
                [
                    GameVisibility(owned_game=item, community=community)
                    for i, item in enumerate(copies)
                    if i % 4 != 1
                ]
            )
            with connection.cursor() as cursor:
                # Model steady-state GIN indexes: autovacuum cannot flush this
                # fixture's uncommitted bulk insert while we hold the transaction.
                for index_name in ("game_title_trgm", "alias_title_trgm"):
                    cursor.execute("SELECT gin_clean_pending_list(%s::regclass)", [index_name])
                for table in (
                    "catalogue_game",
                    "catalogue_gamealias",
                    "inventory_ownedgame",
                    "inventory_gamevisibility",
                    "identity_user",
                    "communities_membership",
                    "communities_community",
                    "loans_loan",
                ):
                    cursor.execute(f"ANALYZE {table}")
                cursor.execute("SHOW server_version")
                postgres = cursor.fetchone()[0]
            # Plans are measured inside the same synthetic transaction, outside
            # HTTP's per-statement budget, so a regression remains diagnosable.
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL jit = off")
            plans = {
                "selective": search(reader, "zyxwvu")[:10].explain(analyze=True, buffers=True),
                "catalogue": search(reader, "palais fictif 00042")[:10].explain(
                    analyze=True, buffers=True
                ),
                "borrow": grouped(borrowable(reader), "royuame synthetique 00042")[:30].explain(
                    analyze=True, buffers=True
                ),
            }
            from pathlib import Path

            Path("work").mkdir(exist_ok=True)
            Path("work/search-benchmark-plans.json").write_text(json.dumps(plans, indent=2))
            client = Client()
            client.force_login(reader)
            measurements = []
            for path in ("/games/", "/copies/"):
                for title in (
                    "ro",
                    "royaume synthetique 00042",
                    "palais fictif 00042",
                    "royuame synthetique 00042",
                ):
                    elapsed: list[float] = []
                    sql_counts = []
                    for index in range(samples + 2):
                        with CaptureQueriesContext(connection) as captured:
                            start = time.perf_counter()
                            response = client.get(path, {"title": title})
                            duration = (time.perf_counter() - start) * 1000
                        if response.status_code != 200:
                            raise CommandError("Échec du rendu mesuré.")
                        if index >= 2:
                            elapsed.append(duration)
                            sql_counts.append(len(captured))
                    p95 = round(sorted(elapsed)[math.ceil(0.95 * samples) - 1], 2)
                    self.stderr.write(f"Measured {path}: p95={p95:.2f}ms")
                    measurements.append(
                        {
                            "path": path,
                            "query": title,
                            "p50_ms": round(statistics.median(elapsed), 2),
                            "p95_ms": p95,
                            "sql_min": min(sql_counts),
                            "sql_max": max(sql_counts),
                        }
                    )
            result = {
                "games": volume,
                "aliases": volume * 3,
                "copies": volume * 4,
                "samples": samples,
                "p95_budget_ms": options["p95_budget_ms"],
                "warmups": 2,
                "postgres": postgres,
                "machine": platform.platform(),
                "processor": platform.processor(),
                "measurements": measurements,
                "plans": plans,
                "protocol": (
                    "Single process, warm cache, authenticated HTML GET "
                    "including SQL/count/render; "
                    "synthetic transaction rolled back."
                ),
            }
            transaction.set_rollback(True)
        self.stdout.write(json.dumps(result, ensure_ascii=True, indent=2))
        if max(row["p95_ms"] for row in measurements) > options["p95_budget_ms"]:
            raise CommandError("Budget de latence p95 dépassé ; rapport conservé, corpus annulé.")
