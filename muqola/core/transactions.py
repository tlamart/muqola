"""Sérialisation courte des écritures métier du petit monolithe PostgreSQL."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

from muqola.identity.models import User


def verified(user: User, *, require_adult: bool = True, allow_restricted: bool = False) -> None:
    query = User.objects.filter(pk=user.pk, is_active=True, email_verified_at__isnull=False)
    if not allow_restricted:
        query = query.filter(deletion_restricted_at__isnull=True)
    if require_adult:
        query = query.filter(adult_confirmed_at__isnull=False)
    if not query.exists():
        raise PermissionDenied


@contextmanager
def domain_write(
    user: User, *, require_adult: bool = True, allow_restricted: bool = False
) -> Iterator[None]:
    # Toutes les écritures communautés/catalogue/exemplaires/prêts prennent ce
    # verrou transactionnel en premier. Pas d'IO externe dans cette section.
    # Choix MVP : débit d'écriture réduit, ordre de verrouillage simple et sûr.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(74821, 1)")
        verified(user, require_adult=require_adult, allow_restricted=allow_restricted)
        yield
