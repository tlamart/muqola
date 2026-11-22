from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

# Toutes les futures routes métier sont fermées par défaut, y compris aux opérateurs non vérifiés.
PUBLIC_VIEWS = {"home", "legal", "health-live", "health-ready", "communities:receive-invite"} | {
    "identity:" + name
    for name in (
        "adult",
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
        if request.user.deletion_restricted_at is not None:
            permitted = match is not None and (
                match.view_name in {"loans:index", "loans:detail", "identity:profile"}
                or (
                    match.view_name == "loans:action"
                    and view_kwargs.get("action") in {"cancel", "decline", "handover", "return"}
                )
            )
            if not permitted:
                return redirect("identity:profile")
        if request.user.adult_confirmed_at is None:
            # Existing loans can still be read/closed without a false attestation.
            legacy_loan = match is not None and (
                match.view_name in {"loans:index", "loans:detail", "identity:profile"}
                or (
                    match.view_name == "loans:action"
                    and view_kwargs.get("action") in {"cancel", "decline", "handover", "return"}
                )
            )
            if not legacy_loan:
                return redirect("identity:adult")
        return None
