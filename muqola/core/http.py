from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from muqola.identity.models import User


def actor(request: HttpRequest) -> User:
    if not request.user.is_authenticated:
        raise PermissionDenied
    return request.user
