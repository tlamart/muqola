import uuid

from django.conf import settings
from django.db import models


class OwnedGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey("catalogue.Game", on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notes = models.CharField(max_length=500, blank=True)
    withdrawn = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["game__title_key", "id"]

    @property
    def available(self) -> bool:
        return (
            not self.withdrawn
            and not self.archived
            and not self.game.hidden
            and not self._has_active_loan()
        )

    def _has_active_loan(self) -> bool:
        # Les lectures en liste réutilisent Exists ; les instances isolées gardent
        # une lecture fraîche des prêts (notamment dans les transactions métier).
        if "has_active_loan" in self.__dict__:
            return bool(self.__dict__["has_active_loan"])
        return self.loans.filter(state__in=["ACCEPTED", "HANDED_OVER"]).exists()


class GameVisibility(models.Model):
    owned_game = models.ForeignKey(OwnedGame, on_delete=models.CASCADE, related_name="visibilities")
    community = models.ForeignKey("communities.Community", on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owned_game", "community"], name="copy_community_unique"
            )
        ]
