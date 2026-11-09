import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


@require_safe
def health_live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_safe
def health_ready(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("database_unavailable")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    return render(
        request,
        "identity/message.html",
        {
            "title": "Formulaire expiré",
            "message": "Rechargez la page et réessayez. Aucune modification n'a été effectuée.",
        },
        status=403,
    )
