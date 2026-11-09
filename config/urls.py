from django.urls import path

from muqola.core.views import health_live, health_ready, home

urlpatterns = [
    path("", home, name="home"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
]
