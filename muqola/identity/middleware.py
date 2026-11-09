from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

# Toutes les futures routes métier sont fermées par défaut, y compris aux opérateurs non vérifiés.
PUBLIC_VIEWS = {"home", "health-live", "health-ready"} | {
    "identity:" + name
    for name in (
        "signup",
        "signup-done",
        "login",
        "logout",
        "pending",
        "resend",
        "email-sent",
        "verify",
        "verify-confirm",
        "verified",
        "reset-request",
        "reset",
        "reset-confirm",
        "reset-done",
    )
}


class VerifiedAccountMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponse],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        match = request.resolver_match
        if match is not None and match.view_name in PUBLIC_VIEWS:
            return None
        if not request.user.is_authenticated:
            return redirect("identity:login")
        if not request.user.is_active or not request.user.email_verified_at:
            return render(request, "identity/unverified.html", status=403)
        return None
