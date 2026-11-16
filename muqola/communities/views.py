import re
from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from muqola.communities import services
from muqola.communities.forms import CommunityForm, InviteForm
from muqola.communities.models import Membership, PendingJoin
from muqola.core.http import actor
from muqola.identity.ratelimit import allowed
from muqola.identity.services import token_digest
from muqola.identity.views import throttled


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    members = (
        Membership.objects.select_related("community")
        .filter(user=actor(request), active=True)
        .annotate(
            member_count=Count(
                "community__memberships",
                filter=Q(
                    community__memberships__active=True,
                    community__memberships__user__is_active=True,
                    community__memberships__user__email_verified_at__isnull=False,
                ),
            )
        )
    )
    return render(request, "communities/index.html", {"memberships": members})


@require_http_methods(["GET", "POST"])
def create(request: HttpRequest) -> HttpResponse:
    form = CommunityForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not allowed(request, "community", actor(request).email):
            return throttled(request, "community")
        community = services.create(actor(request), **form.cleaned_data)
        messages.success(request, "Votre communauté privée est créée.")
        return redirect("communities:detail", community_id=community.pk)
    return render(request, "communities/create.html", {"form": form})


@require_http_methods(["GET", "POST"])
def detail(request: HttpRequest, community_id: UUID) -> HttpResponse:
    member = services.membership(actor(request), community_id)
    admin = member.role == Membership.Role.ADMIN
    form = CommunityForm(
        initial={
            "name": member.community.name,
            "description": member.community.description,
            "illustration": member.community.illustration,
        }
    )
    invite_form = InviteForm()
    if request.method == "POST":
        services.membership(actor(request), community_id, admin=True)
        if request.POST.get("action") == "invite":
            if not allowed(request, "invite", actor(request).email):
                return throttled(request, "invite")
            invite_form = InviteForm(request.POST)
            if invite_form.is_valid():
                services.invite(actor(request), community_id, **invite_form.cleaned_data)
                return redirect("communities:detail", community_id=community_id)
        else:
            form = CommunityForm(request.POST)
            if form.is_valid():
                services.update(actor(request), community_id, **form.cleaned_data)
                return redirect("communities:detail", community_id=community_id)
    invitation, link = services.current_invitation(actor(request), community_id)
    return render(
        request,
        "communities/detail.html",
        {
            "community": member.community,
            "admin": admin,
            "form": form,
            "invite_form": invite_form,
            "members": Membership.objects.filter(
                community_id=community_id, active=True
            ).select_related("user"),
            "invitation": invitation,
            "invitation_link": link,
        },
    )


@require_GET
def receive_invite(request: HttpRequest, raw: str) -> HttpResponse:
    if not allowed(request, "token"):
        response = throttled(request)
    elif not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
        response = render(request, "communities/invalid.html", status=400)
    else:
        digest = token_digest(raw)
        request.session["community_invite"] = digest
        if request.user.is_authenticated:
            services.remember(actor(request), digest)
            response = redirect(
                "communities:join" if actor(request).email_verified_at else "identity:pending"
            )
        else:
            response = redirect("identity:login")
    response["Referrer-Policy"] = "no-referrer"
    return response


def pending_digest(request: HttpRequest) -> str:
    if request.session.get("community_invite"):
        return str(request.session["community_invite"])
    pending = PendingJoin.objects.filter(user=actor(request)).first()
    return pending.digest if pending else ""


@require_http_methods(["GET", "POST"])
def join(request: HttpRequest) -> HttpResponse:
    digest = pending_digest(request)
    item = services.valid_invite(digest)
    if item is None:
        return render(request, "communities/invalid.html", status=400)
    if request.method == "POST":
        if not allowed(request, "invite", actor(request).email):
            return throttled(request, "invite")
        try:
            community = services.join(actor(request), digest)
        except ValidationError:
            return render(request, "communities/invalid.html", status=400)
        request.session.pop("community_invite", None)
        messages.success(request, "Vous avez rejoint la communauté.")
        return redirect("communities:detail", community_id=community.pk)
    return render(request, "communities/join.html", {"community": item.community})


@require_POST
def member_action(
    request: HttpRequest, community_id: UUID, action: str, target_id: int
) -> HttpResponse:
    try:
        if action == "transfer":
            services.transfer(actor(request), community_id, target_id)
        else:
            services.remove(actor(request), community_id, target_id)
    except ValidationError as error:
        return render(
            request, "domain_error.html", {"message": " ".join(error.messages)}, status=400
        )
    return redirect("communities:index")


@require_POST
def revoke(request: HttpRequest, community_id: UUID, invite_id: UUID) -> HttpResponse:
    services.membership(actor(request), community_id, admin=True)
    if not allowed(request, "invite", actor(request).email):
        return throttled(request, "invite")
    services.revoke(actor(request), community_id, invite_id)
    return redirect("communities:detail", community_id=community_id)
