import re

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from muqola.identity.forms import EmailForm, LoginForm, PasswordForm, SignupForm
from muqola.identity.models import AccountToken
from muqola.identity.ratelimit import LIMITS, allowed
from muqola.identity.services import (
    consume_token,
    register,
    request_token,
    token_digest,
    usable_token,
)


def throttled(request: HttpRequest, action: str = "token") -> HttpResponse:
    response = render(
        request,
        "identity/message.html",
        {
            "title": "Veuillez patienter",
            "message": "Trop de tentatives. Réessayez plus tard.",
        },
        status=429,
    )
    duration = LIMITS[action][0]
    response["Retry-After"] = str(duration - int(timezone.now().timestamp()) % duration)
    return response


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.method == "POST" and not allowed(request, "signup", request.POST.get("email", "")):
        return throttled(request, "signup")
    form = SignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        register(
            form.cleaned_data["email"],
            form.cleaned_data["display_name"],
            form.cleaned_data["password"],
        )
        return redirect("identity:signup-done")
    return render(
        request,
        "identity/form.html",
        {"form": form, "title": "Créer mon compte", "submit": "S'inscrire", "kind": "signup"},
    )


@require_http_methods(["GET", "POST"])
def sign_in(request: HttpRequest) -> HttpResponse:
    if request.method == "POST" and not allowed(request, "login", request.POST.get("email", "")):
        return throttled(request, "login")
    form = LoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request, username=form.cleaned_data["email"], password=form.cleaned_data["password"]
        )
        if user is not None:
            login(request, user)
            return redirect("identity:dashboard" if user.email_verified_at else "identity:pending")
        form.add_error(None, "Adresse ou mot de passe incorrect.")
    return render(
        request,
        "identity/form.html",
        {"form": form, "title": "Se connecter", "submit": "Se connecter", "kind": "login"},
    )


@require_POST
def sign_out(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("home")


@require_GET
@login_required(login_url="identity:login")
def pending(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and request.user.email_verified_at:
        return redirect("identity:dashboard")
    return render(request, "identity/unverified.html")


@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "identity/dashboard.html")


@require_http_methods(["GET", "POST"])
def email_request(request: HttpRequest, purpose: str) -> HttpResponse:
    action = "resend" if purpose == AccountToken.Purpose.VERIFY else "reset"
    if request.method == "POST" and not allowed(request, action, request.POST.get("email", "")):
        return throttled(request, action)
    form = EmailForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        request_token(form.cleaned_data["email"], purpose)
        return redirect("identity:email-sent")
    title = "Recevoir un nouveau lien" if action == "resend" else "Mot de passe oublié"
    return render(
        request, "identity/form.html", {"form": form, "title": title, "submit": "Envoyer le lien"}
    )


@require_GET
def receive_token(request: HttpRequest, raw_token: str, purpose: str) -> HttpResponse:
    # Un GET ne consomme jamais le jeton ; limiter aussi les créations de session.
    if not allowed(request, "token"):
        response = throttled(request)
    elif not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw_token):
        response = invalid_link(request)
    else:
        request.session[f"account_{purpose}"] = token_digest(raw_token)
        response = redirect(
            "identity:verify-confirm"
            if purpose == AccountToken.Purpose.VERIFY
            else "identity:reset-confirm"
        )
    # Aucun référent depuis l'URL portant le secret. La page propre rétablit
    # same-origin pour permettre aux navigateurs de transmettre un Origin CSRF valide.
    response["Referrer-Policy"] = "no-referrer"
    return response


def invalid_link(request: HttpRequest) -> HttpResponse:
    return render(request, "identity/invalid_link.html", status=400)


@require_http_methods(["GET", "POST"])
def confirm_verify(request: HttpRequest) -> HttpResponse:
    digest = str(request.session.get("account_verify", ""))
    if request.method == "POST":
        if not allowed(request, "token"):
            return throttled(request)
        if consume_token(digest, AccountToken.Purpose.VERIFY):
            request.session.pop("account_verify", None)
            return redirect("identity:verified")
        return invalid_link(request)
    if usable_token(digest, AccountToken.Purpose.VERIFY) is None:
        return invalid_link(request)
    return render(request, "identity/verify.html")


@require_http_methods(["GET", "POST"])
def confirm_reset(request: HttpRequest) -> HttpResponse:
    digest = str(request.session.get("account_reset", ""))
    if request.method == "POST" and not allowed(request, "token"):
        return throttled(request)
    token = usable_token(digest, AccountToken.Purpose.RESET)
    if token is None:
        return invalid_link(request)
    form = PasswordForm(request.POST if request.method == "POST" else None, user=token.user)
    if request.method == "POST" and form.is_valid():
        if not consume_token(digest, AccountToken.Purpose.RESET, form.cleaned_data["password"]):
            return invalid_link(request)
        # Pas de connexion implicite ; le nouveau hash invalide les anciennes sessions.
        logout(request)
        return redirect("identity:reset-done")
    return render(
        request,
        "identity/form.html",
        {
            "form": form,
            "title": "Choisir un nouveau mot de passe",
            "submit": "Enregistrer mon mot de passe",
        },
    )


@require_GET
def message(request: HttpRequest, title: str, text: str) -> HttpResponse:
    return render(request, "identity/message.html", {"title": title, "message": text})
