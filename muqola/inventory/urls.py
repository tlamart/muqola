from django.urls import path

from muqola.catalogue.views import detail as game_detail
from muqola.inventory import views
from muqola.loans.views import request_loan

app_name = "inventory"
urlpatterns = [
    path("<uuid:copy_id>/request/", request_loan, name="request"),
    path("<uuid:copy_id>/archive/", views.archive, name="archive"),
    path("", views.index, name="index"),
    path("games/<uuid:game_id>/", game_detail, {"borrowing": True}, name="game"),
    path("mine/", views.mine, name="mine"),
    path("<uuid:copy_id>/", views.detail, name="detail"),
    path("<uuid:copy_id>/edit/", views.edit, name="edit"),
]
