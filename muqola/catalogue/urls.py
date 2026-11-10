from django.urls import path

from muqola.catalogue import views
from muqola.inventory.views import edit

app_name = "catalogue"
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.edit, name="create"),
    path("<uuid:game_id>/", views.detail, name="detail"),
    path("<uuid:game_id>/edit/", views.edit, name="edit"),
    path("<uuid:game_id>/report/", views.report, name="report"),
    path("<uuid:game_id>/add-copy/", edit, name="add-copy"),
]
