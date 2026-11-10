import unicodedata
import uuid
from typing import Any

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def normalized_title(value: str) -> str:
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(c)
        ).split()
    )


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    title_key = models.CharField(max_length=300, db_index=True, editable=False)
    publisher = models.CharField(max_length=120, blank=True)
    year = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(2200)]
    )
    players_min = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    players_max = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    duration = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10000)]
    )
    description = models.CharField(max_length=2000, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ever_reused = models.BooleanField(default=False, editable=False)
    hidden = models.BooleanField(default=False)
    external_source = models.CharField(max_length=80, null=True, blank=True)
    external_id = models.CharField(max_length=120, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title_key", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(players_min__isnull=True)
                | models.Q(players_max__isnull=True)
                | models.Q(players_max__gte=models.F("players_min")),
                name="game_players_order",
            ),
            models.UniqueConstraint(
                fields=["external_source", "external_id"],
                condition=models.Q(external_source__isnull=False, external_id__isnull=False),
                name="game_external_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(external_source__isnull=True, external_id__isnull=True)
                | models.Q(external_source__isnull=False, external_id__isnull=False),
                name="game_external_pair",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.title_key = normalized_title(self.title)
        super().save(*args, **kwargs)


class GameReport(models.Model):
    game = models.ForeignKey(Game, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "created_by"],
                condition=models.Q(resolved_at__isnull=True),
                name="game_report_pending_unique",
            )
        ]
