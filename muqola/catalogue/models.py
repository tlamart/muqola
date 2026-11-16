import unicodedata
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from muqola.catalogue.commons import validate_illustration


def normalized_title(value: str) -> str:
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(c)
        ).split()
    )


class Game(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente de validation"
        APPROVED = "approved", "Validée"
        REJECTED = "rejected", "À corriger / refusée"
        LEGACY = "legacy_to_review", "Fiche héritée à réviser"

    class Kind(models.TextChoices):
        UNKNOWN = "unknown", "Je ne sais pas"
        STANDALONE = "standalone", "Jeu autonome"
        EXPANSION = "expansion", "Extension nécessitant un jeu de base"
        STANDALONE_EXPANSION = "standalone_expansion", "Extension jouable seule"

    moderation_status = models.CharField(
        max_length=20, choices=Status, default=Status.PENDING, db_index=True
    )
    kind = models.CharField(max_length=24, choices=Kind, default=Kind.UNKNOWN)
    base_game = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="expansions"
    )
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="merged_sources"
    )
    proposal_reason = models.CharField(max_length=500, blank=True)
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
    data_source = models.CharField(max_length=80, blank=True)
    data_license = models.CharField(max_length=80, blank=True)
    bgg_ids = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title_key", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    moderation_status__in=["pending", "approved", "rejected", "legacy_to_review"]
                ),
                name="game_moderation_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=["unknown", "standalone", "expansion", "standalone_expansion"]
                ),
                name="game_kind_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(moderation_status="approved") | ~models.Q(kind="unknown"),
                name="approved_game_known_kind",
            ),
            models.CheckConstraint(
                condition=~models.Q(moderation_status="approved", kind="expansion")
                | models.Q(base_game__isnull=False),
                name="approved_expansion_base",
            ),
            models.CheckConstraint(
                condition=~models.Q(base_game=models.F("id")), name="game_no_self_base"
            ),
            models.CheckConstraint(
                condition=~models.Q(merged_into=models.F("id")), name="game_no_self_merge"
            ),
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

    def __str__(self) -> str:
        return self.title

    @property
    def lendable(self) -> bool:
        return (
            not self.hidden
            and self.merged_into_id is None
            and self.moderation_status in (self.Status.APPROVED, self.Status.LEGACY)
        )

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError({"title": "Le titre est obligatoire."})
        if self.moderation_status == self.Status.APPROVED and self.kind == self.Kind.UNKNOWN:
            raise ValidationError({"kind": "Précisez le type avant validation."})
        if (
            self.moderation_status == self.Status.APPROVED
            and self.kind == self.Kind.EXPANSION
            and not self.base_game_id
        ):
            raise ValidationError({"base_game": "Le jeu de base est obligatoire."})
        if self.base_game_id and self.kind != self.Kind.EXPANSION:
            raise ValidationError(
                {"base_game": "Seules les extensions dépendantes nécessitent une base."}
            )
        seen = {self.pk}
        current = self.base_game_id
        while current:
            if current in seen:
                raise ValidationError(
                    {"base_game": "Une relation de base ne peut pas former un cycle."}
                )
            seen.add(current)
            parent = (
                Game.objects.filter(pk=current)
                .values("base_game_id", "merged_into_id", "moderation_status", "hidden")
                .first()
            )
            if parent is None:
                break  # FK validation reports the missing row.
            if parent["merged_into_id"]:
                raise ValidationError(
                    {"base_game": "Choisissez la fiche canonique du jeu de base."}
                )
            if self.moderation_status == self.Status.APPROVED and (
                parent["moderation_status"] != self.Status.APPROVED or parent["hidden"]
            ):
                raise ValidationError(
                    {"base_game": "Le jeu de base doit être validé et non masqué."}
                )
            current = parent["base_game_id"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.title_key = normalized_title(self.title)
        super().save(*args, **kwargs)


class GameAlias(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="aliases")
    title = models.CharField(max_length=120)
    title_key = models.CharField(max_length=300, db_index=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "title_key"], name="game_alias_unique")
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.title_key = normalized_title(self.title)
        super().save(*args, **kwargs)


class GameIllustration(models.Model):
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="illustration")
    image_url = models.URLField(max_length=1000)
    commons_file = models.CharField(max_length=255)
    source_url = models.URLField(max_length=1000)
    license = models.CharField(max_length=80)
    license_url = models.URLField(max_length=255)
    artist = models.CharField(max_length=500, blank=True)
    attribution = models.CharField(max_length=1000, blank=True)
    review_status = models.CharField(max_length=32, default="approved_by_owner")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(review_status="approved_by_owner"),
                name="game_illustration_approved",
            )
        ]

    def clean(self) -> None:
        validate_illustration(
            self.image_url,
            self.commons_file,
            self.source_url,
            self.license,
            self.license_url,
            self.artist,
            self.attribution,
            self.review_status,
        )

    @property
    def displayable(self) -> bool:
        try:
            self.clean()
        except ValidationError:
            return False
        return True


class GameReport(models.Model):
    original_game = models.ForeignKey(
        Game, on_delete=models.PROTECT, related_name="original_reports"
    )
    game = models.ForeignKey(Game, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.original_game_id:
            self.original_game_id = self.game_id
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["original_game", "created_by"],
                condition=models.Q(resolved_at__isnull=True),
                name="game_report_pending_unique",
            )
        ]


class GameExternalIdentifier(models.Model):
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="external_identifiers")
    source = models.CharField(max_length=80)
    identifier = models.CharField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "identifier"], name="catalogue_external_identifier_unique"
            )
        ]


class GameDecision(models.Model):
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="decisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Game.Status)
    reason = models.CharField(max_length=500)
    homonym_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class GameMerge(models.Model):
    source = models.OneToOneField(Game, on_delete=models.PROTECT, related_name="merge_record")
    target = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="merge_history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    references = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
