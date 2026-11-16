from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from muqola.catalogue import services
from muqola.catalogue.forms import GameForm, QuickAddForm, ReportForm
from muqola.catalogue.models import Game, GameIllustration
from muqola.communities.models import Membership
from muqola.core.http import actor
from muqola.core.search import bounded_search
from muqola.inventory.models import GameVisibility
from muqola.inventory.services import add_to_collection, available, borrowable, visible


@require_http_methods(["GET", "POST"])
@bounded_search
def index(request: HttpRequest) -> HttpResponse:
    title = request.GET.get("title", "")[:120]
    manual = request.GET.get("manual") == "1"
    matches = services.search(actor(request), title)
    form = QuickAddForm(
        request.POST if request.method == "POST" else None,
        user=actor(request),
        initial={"title": title} if manual else None,
    )
    if request.method == "POST" and request.FILES:
        form.add_error(None, "Les fichiers et photos utilisateur ne sont pas acceptés.")
    if request.method == "POST" and form.is_valid():
        try:
            saved = add_to_collection(
                actor(request),
                form.cleaned_data["game_id"],
                form.cleaned_data["title"],
                form.cleaned_data["notes"],
                [UUID(value) for value in form.cleaned_data["communities"]],
                form.cleaned_data["proposal_reason"],
            )
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Jeu ajouté à votre collection.")
            return redirect("inventory:detail", copy_id=saved.pk)
    return render(
        request,
        "catalogue/results.html"
        if request.method == "GET" and request.headers.get("X-Requested-With") == "live-search"
        else "catalogue/index.html",
        {
            "games": Paginator(matches, 10).get_page(request.GET.get("page")),
            "title_query": title,
            "form": form,
            "manual": manual,
        },
        status=400 if request.method == "POST" else 200,
    )


@require_http_methods(["GET", "POST"])
def edit(request: HttpRequest, game_id: UUID | None = None) -> HttpResponse:
    game = (
        get_object_or_404(
            Game,
            pk=game_id,
            created_by=actor(request),
            hidden=False,
            merged_into__isnull=True,
            moderation_status__in=[Game.Status.PENDING, Game.Status.REJECTED],
        )
        if game_id
        else None
    )
    form = GameForm(request.POST if request.method == "POST" else None, instance=game)
    if request.method == "POST" and request.FILES:
        form.add_error(None, "Les fichiers et photos utilisateur ne sont pas acceptés.")
    if request.method == "POST" and form.is_valid():
        try:
            data = dict(form.cleaned_data)
            data["base_game_id"] = data.pop("base_game").pk if data.get("base_game") else None
            data["aliases"] = data.pop("alternate_titles", "").splitlines()
            saved = services.write_game(actor(request), data, game_id)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Fiche de jeu enregistrée.")
            return redirect("catalogue:detail", game_id=saved.pk)
    return render(
        request,
        "domain_form.html",
        {
            "form": form,
            "title": "Corriger une fiche" if game else "Créer une fiche de jeu",
            "notice": "Votre proposition reste privée jusqu'à validation par la plateforme. "
            "Seul le titre est obligatoire ; une édition commerciale ne "
            "justifie pas une nouvelle fiche.",
            "suggestions": services.search(
                actor(request), request.POST.get("title", request.GET.get("title", ""))[:120]
            )[:10]
            if not game and (request.POST.get("title") or request.GET.get("title"))
            else [],
        },
        status=400 if request.method == "POST" else 200,
    )


@require_GET
def detail(request: HttpRequest, game_id: UUID, borrowing: bool = False) -> HttpResponse:
    if borrowing:
        get_object_or_404(
            Game.objects.filter(pk__in=borrowable(actor(request)).values("game_id")), pk=game_id
        )
    game = services.canonical(actor(request), game_id)
    if game.pk != game_id:
        return redirect("catalogue:detail", game_id=game.pk)
    accessible = (borrowable(actor(request)) if borrowing else visible(actor(request))).filter(
        game=game
    )
    copies = Paginator(accessible, 30).get_page(request.GET.get("page"))
    page_copies = list(copies)
    # Les noms de communautés sont eux-mêmes privés : seulement celles du lecteur.
    shared = GameVisibility.objects.filter(
        owned_game__in=page_copies,
        community_id__in=Membership.objects.filter(user=actor(request), active=True).values(
            "community_id"
        ),
    ).select_related("community")
    communities_by_copy: dict[UUID, list[str]] = {}
    for visibility in shared:
        communities_by_copy.setdefault(visibility.owned_game_id, []).append(
            visibility.community.name
        )
    copy_rows = [
        {
            "copy": item,
            "available": item.available,
            "communities": communities_by_copy.get(item.pk, []),
        }
        for item in page_copies
    ]
    return render(
        request,
        "catalogue/detail.html",
        {
            "game": game,
            "copies": copies,
            "copy_rows": copy_rows,
            "has_available": available(accessible).exists(),
            "can_edit": game.created_by_id == actor(request).pk
            and game.moderation_status in (Game.Status.PENDING, Game.Status.REJECTED),
            "can_add": game.moderation_status == Game.Status.APPROVED
            or (
                game.moderation_status == Game.Status.PENDING
                and game.created_by_id == actor(request).pk
            ),
            "private_proposal": game.moderation_status
            in (Game.Status.PENDING, Game.Status.REJECTED),
            "decisions": game.decisions.all()[:10]
            if game.moderation_status in (Game.Status.PENDING, Game.Status.REJECTED)
            and (game.created_by_id == actor(request).pk or actor(request).is_superuser)
            else [],
            "retained_illustrations": GameIllustration.objects.filter(
                game__merged_into=game, game__hidden=False
            ).select_related("game", "game__illustration"),
        },
    )


@require_http_methods(["GET", "POST"])
def report(request: HttpRequest, game_id: UUID) -> HttpResponse:
    services.canonical(actor(request), game_id)
    form = ReportForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        services.report(actor(request), game_id, form.cleaned_data["reason"])
        messages.success(request, "Votre signalement est enregistré pour maintenance.")
        return redirect("catalogue:detail", game_id=game_id)
    return render(
        request, "domain_form.html", {"form": form, "title": "Signaler ou proposer une correction"}
    )


@require_GET
def proposals(request: HttpRequest) -> HttpResponse:
    query = Game.objects.filter(created_by=actor(request)).order_by("-updated_at", "id")
    return render(
        request,
        "catalogue/proposals.html",
        {"games": Paginator(query, 20).get_page(request.GET.get("page"))},
    )
