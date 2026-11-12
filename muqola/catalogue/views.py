from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from muqola.catalogue import services
from muqola.catalogue.forms import GameForm, ReportForm
from muqola.catalogue.models import Game
from muqola.communities.models import Membership
from muqola.core.http import actor
from muqola.inventory.models import GameVisibility
from muqola.inventory.services import available, visible


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    title = request.GET.get("title", "")[:120]
    return render(
        request,
        "catalogue/index.html",
        {
            "games": Paginator(services.search(actor(request), title), 30).get_page(
                request.GET.get("page")
            ),
            "title_query": title,
        },
    )


@require_http_methods(["GET", "POST"])
def edit(request: HttpRequest, game_id: UUID | None = None) -> HttpResponse:
    game = (
        get_object_or_404(Game, pk=game_id, created_by=actor(request), hidden=False)
        if game_id
        else None
    )
    form = GameForm(request.POST if request.method == "POST" else None, instance=game)
    if request.method == "POST" and form.is_valid():
        try:
            saved = services.write_game(actor(request), form.cleaned_data, game_id)
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
            "notice": "Cette fiche générique est visible à tous les comptes vérifiés. "
            "N'y saisissez aucune donnée personnelle. Recherchez d'abord une fiche existante.",
        },
    )


@require_GET
def detail(request: HttpRequest, game_id: UUID) -> HttpResponse:
    game = get_object_or_404(services.search(actor(request)), pk=game_id)
    accessible = visible(actor(request)).filter(game=game)
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
            "can_edit": game.created_by_id == actor(request).pk and not game.ever_reused,
        },
    )


@require_http_methods(["GET", "POST"])
def report(request: HttpRequest, game_id: UUID) -> HttpResponse:
    get_object_or_404(services.search(actor(request)), pk=game_id)
    form = ReportForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        services.report(actor(request), game_id, form.cleaned_data["reason"])
        messages.success(request, "Votre signalement est enregistré pour maintenance.")
        return redirect("catalogue:detail", game_id=game_id)
    return render(
        request, "domain_form.html", {"form": form, "title": "Signaler ou proposer une correction"}
    )
