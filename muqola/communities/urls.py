from django.urls import path

from muqola.communities import views

app_name = "communities"
urlpatterns = [
    path("", views.index, name="index"),
    path("invite/<str:raw>/", views.receive_invite, name="receive-invite"),
    path("join/", views.join, name="join"),
    path("<uuid:community_id>/", views.detail, name="detail"),
    path(
        "<uuid:community_id>/remove/<int:target_id>/",
        views.member_action,
        {"action": "remove"},
        name="remove",
    ),
    path(
        "<uuid:community_id>/transfer/<int:target_id>/",
        views.member_action,
        {"action": "transfer"},
        name="transfer",
    ),
    path("<uuid:community_id>/revoke/<uuid:invite_id>/", views.revoke, name="revoke"),
]
