import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Loan(models.Model):
    class State(models.TextChoices):
        REQUESTED = "REQUESTED", "Demandé"
        ACCEPTED = "ACCEPTED", "Accepté"
        HANDED_OVER = "HANDED_OVER", "Remis"
        RETURNED = "RETURNED", "Rendu"
        DECLINED = "DECLINED", "Refusé"
        CANCELLED = "CANCELLED", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owned_game = models.ForeignKey(
        "inventory.OwnedGame", on_delete=models.PROTECT, related_name="loans"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="loans_lent"
    )
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="loans_borrowed"
    )
    state = models.CharField(max_length=12, choices=State.choices, default=State.REQUESTED)
    due_date = models.DateField()
    message = models.CharField(max_length=500, blank=True)
    close_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    handed_over_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["owner", "state"], name="loan_owner_state_idx"),
            models.Index(fields=["borrower", "state"], name="loan_borrower_state_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owned_game"],
                condition=models.Q(state__in=["ACCEPTED", "HANDED_OVER"]),
                name="one_active_loan_per_copy",
            ),
            models.UniqueConstraint(
                fields=["owned_game", "borrower"],
                condition=models.Q(state="REQUESTED"),
                name="one_pending_request_per_borrower",
            ),
            models.CheckConstraint(
                condition=~models.Q(owner=models.F("borrower")), name="loan_no_self_borrow"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "REQUESTED",
                        "ACCEPTED",
                        "HANDED_OVER",
                        "RETURNED",
                        "DECLINED",
                        "CANCELLED",
                    ]
                ),
                name="loan_state_valid",
            ),
        ]

    @property
    def active(self) -> bool:
        return self.state in (self.State.ACCEPTED, self.State.HANDED_OVER)


class LoanEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    state = models.CharField(max_length=12, choices=Loan.State.choices)
    reason = models.CharField(max_length=500, blank=True)
    administrative = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
