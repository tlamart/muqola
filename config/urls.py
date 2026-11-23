from django.urls import include, path

from muqola.core.views import health_live, health_ready, home, legal
from muqola.operations.catalogue_admin import catalogue_admin

urlpatterns = [
    path("operator/", catalogue_admin.urls),
    path("legal/<slug:document>/", legal, name="legal"),
    path("loans/", include("muqola.loans.urls")),
    path("games/", include("muqola.catalogue.urls")),
    path("copies/", include("muqola.inventory.urls")),
    path("communities/", include("muqola.communities.urls")),
    path("accounts/", include("muqola.identity.urls")),
    path("", home, name="home"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
]
