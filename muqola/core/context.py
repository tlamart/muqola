"""Small deployment label, without exposing configuration or secrets."""

from django.conf import settings
from django.http import HttpRequest


def deployment(request: HttpRequest) -> dict[str, bool]:
    return {"is_staging": settings.DEPLOYMENT_ENV == "staging"}
