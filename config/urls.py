from django.urls import include, path

from muqola.core.views import health_live, health_ready, home

urlpatterns = [
    path("loans/", include("muqola.loans.urls")),
    path("games/", include("muqola.catalogue.urls")),
    path("copies/", include("muqola.inventory.urls")),
    path("communities/", include("muqola.communities.urls")),
    path("accounts/", include("muqola.identity.urls")),
    path("", home, name="home"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
]
