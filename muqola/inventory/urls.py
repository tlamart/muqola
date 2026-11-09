from django.urls import path

from muqola.inventory import views

app_name = "inventory"
urlpatterns = [
    path("", views.index, name="index"),
    path("mine/", views.mine, name="mine"),
    path("<uuid:copy_id>/", views.detail, name="detail"),
    path("<uuid:copy_id>/edit/", views.edit, name="edit"),
]
