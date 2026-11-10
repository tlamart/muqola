from django.http import HttpRequest, HttpResponse
from django.urls import path

from config.urls import urlpatterns as application_patterns


def private_probe(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Donnée métier réservée")


urlpatterns = [
    *application_patterns,
    path("future-business/", private_probe, name="future-business"),
]
