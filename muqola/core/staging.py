"""Synthetic account restriction, independent from public-production rules."""

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_staging_email(email: str) -> None:
    if settings.DEPLOYMENT_ENV == "staging" and not email.lower().endswith("@example.test"):
        raise ValidationError("Staging privé : utilisez une adresse fictive @example.test.")
