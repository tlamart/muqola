"""Comptes, jetons temporaires et budgets de débit partagés."""

import uuid
from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils import timezone


class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        if not email.strip():
            raise ValueError("Une adresse e-mail est obligatoire.")
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Un superutilisateur doit avoir les droits opérateur.")
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    display_name = models.CharField(max_length=80)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]
    objects = UserManager()  # type: ignore[assignment, misc]

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email=Lower(Trim("email"))), name="identity_email_normalized"
            ),
            models.CheckConstraint(condition=~models.Q(email=""), name="identity_email_nonempty"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class AccountToken(models.Model):
    class Purpose(models.TextChoices):
        VERIFY = "verify", "Vérification"
        RESET = "reset", "Réinitialisation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_tokens")
    purpose = models.CharField(max_length=8, choices=Purpose.choices)
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="identity_token_future_expiry",
            ),
            models.CheckConstraint(
                condition=models.Q(purpose__in=["verify", "reset"]), name="identity_token_purpose"
            ),
        ]


class RateBucket(models.Model):
    # HMAC d'une portée, identité réseau/e-mail et fenêtre ; aucune IP/e-mail en clair.
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
