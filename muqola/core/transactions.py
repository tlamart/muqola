"""Sérialisation courte des écritures métier du petit monolithe PostgreSQL."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

from muqola.identity.models import User


def verified(user: User) -> None:
    if not User.objects.filter(
        pk=user.pk, is_active=True, email_verified_at__isnull=False
    ).exists():
        raise PermissionDenied


@contextmanager
def domain_write(user: User) -> Iterator[None]:
    # Toutes les écritures communautés/catalogue/exemplaires/prêts prennent ce
    # verrou transactionnel en premier. Pas d'IO externe dans cette section.
    # Choix MVP : débit d'écriture réduit, ordre de verrouillage simple et sûr.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(74821, 1)")
        verified(user)
        yield
