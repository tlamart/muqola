import uuid

from django.db import models
from django.utils import timezone


class EmailOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        SENT = "sent", "Envoyé"
        DISCARDED = "discarded", "Lien invalide"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.OneToOneField("identity.AccountToken", on_delete=models.CASCADE)
    encrypted_payload = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="outbox_due_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "sent", "discarded"]),
                name="outbox_status_valid",
            )
        ]
