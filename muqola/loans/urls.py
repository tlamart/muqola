from django.urls import path

from muqola.loans import views

app_name = "loans"
urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:loan_id>/", views.detail, name="detail"),
    path("<uuid:loan_id>/<str:action>/", views.action, name="action"),
]
