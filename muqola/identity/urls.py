from django.urls import path

from muqola.identity import views
from muqola.identity.models import AccountToken

app_name = "identity"
urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path(
        "signup/done/",
        views.message,
        {
            "title": "Consultez votre messagerie",
            "text": "Si cette adresse peut être inscrite, "
            "un lien de vérification vous sera envoyé. "
            "Si vous avez déjà un compte, connectez-vous ou demandez un nouveau lien.",
        },
        name="signup-done",
    ),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("pending/", views.pending, name="pending"),
    path("resend/", views.email_request, {"purpose": AccountToken.Purpose.VERIFY}, name="resend"),
    path(
        "email-sent/",
        views.message,
        {
            "title": "Demande enregistrée",
            "text": "Si un compte éligible correspond à cette adresse, un lien vous sera envoyé. "
            "Consultez votre messagerie et vos courriers indésirables.",
        },
        name="email-sent",
    ),
    path("verify/confirm/", views.confirm_verify, name="verify-confirm"),
    path(
        "verify/done/",
        views.message,
        {
            "title": "Adresse e-mail vérifiée",
            "text": "Votre adresse est confirmée. Vous pouvez maintenant vous connecter.",
        },
        name="verified",
    ),
    path(
        "verify/<str:raw_token>/",
        views.receive_token,
        {"purpose": AccountToken.Purpose.VERIFY},
        name="verify",
    ),
    path(
        "reset/", views.email_request, {"purpose": AccountToken.Purpose.RESET}, name="reset-request"
    ),
    path("reset/confirm/", views.confirm_reset, name="reset-confirm"),
    path(
        "reset/done/",
        views.message,
        {
            "title": "Mot de passe enregistré",
            "text": "Vos anciennes sessions sont invalidées. "
            "Connectez-vous avec votre nouveau mot de passe.",
        },
        name="reset-done",
    ),
    path(
        "reset/<str:raw_token>/",
        views.receive_token,
        {"purpose": AccountToken.Purpose.RESET},
        name="reset",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
]
