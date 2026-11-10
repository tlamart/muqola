from django.utils import timezone

from muqola.identity.models import User


def member(name: str = "Alice", verified: bool = True) -> User:
    return User.objects.create(
        email=f"{name.lower()}@example.test",
        display_name=name,
        email_verified_at=timezone.now() if verified else None,
        password="!",
    )
