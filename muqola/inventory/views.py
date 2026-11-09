from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from muqola.catalogue.models import Game, normalized_title
from muqola.core.http import actor
from muqola.inventory import services
from muqola.inventory.forms import CopyForm, SearchForm
from muqola.inventory.models import OwnedGame


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    form = SearchForm(request.GET, user=actor(request))
    copies = services.visible(actor(request))
    if form.is_valid():
        data = form.cleaned_data
        copies = copies.filter(game__title_key__contains=normalized_title(data["title"]))
        if data["community"]:
            copies = copies.filter(visibilities__community_id=data["community"])
        if data["players"]:
            copies = copies.filter(
                Q(game__players_min__isnull=True) | Q(game__players_min__lte=data["players"]),
                Q(game__players_max__isnull=True) | Q(game__players_max__gte=data["players"]),
            )
        if data["only_available"]:
            copies = services.available(copies)
    else:
        copies = copies.none()
    return render(
        request,
        "inventory/index.html",
        {
            "form": form,
            "copies": Paginator(copies.distinct(), 30).get_page(request.GET.get("page")),
        },
        status=200 if form.is_valid() else 400,
    )


@require_GET
def mine(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "inventory/mine.html",
        {
            "copies": Paginator(
                OwnedGame.objects.filter(owner=actor(request), archived=False).select_related(
                    "game"
                ),
                30,
            ).get_page(request.GET.get("page"))
        },
    )


@require_GET
def detail(request: HttpRequest, copy_id: UUID) -> HttpResponse:
    item = get_object_or_404(services.visible(actor(request)), pk=copy_id)
    return render(request, "inventory/detail.html", {"copy": item})


@require_http_methods(["GET", "POST"])
def edit(
    request: HttpRequest, game_id: UUID | None = None, copy_id: UUID | None = None
) -> HttpResponse:
    item = (
        get_object_or_404(OwnedGame, pk=copy_id, owner=actor(request), archived=False)
        if copy_id
        else None
    )
    game = item.game if item else get_object_or_404(Game, pk=game_id, hidden=False)
    initial = (
        {
            "notes": item.notes,
            "withdrawn": item.withdrawn,
            "communities": [
                str(c) for c in item.visibilities.values_list("community_id", flat=True)
            ],
        }
        if item
        else {}
    )
    form = CopyForm(
        request.POST if request.method == "POST" else None, user=actor(request), initial=initial
    )
    if request.method == "POST" and form.is_valid():
        try:
            saved = services.write_copy(
                actor(request),
                game.pk,
                form.cleaned_data["notes"],
                [UUID(value) for value in form.cleaned_data["communities"]],
                form.cleaned_data["withdrawn"],
                copy_id,
            )
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Exemplaire et partage enregistrés.")
            return redirect("inventory:detail", copy_id=saved.pk)
    return render(
        request,
        "domain_form.html",
        {
            "form": form,
            "title": f"Mon exemplaire de {game.title}",
            "notice": "Sans communauté sélectionnée, cet exemplaire reste privé. "
            "Plusieurs exemplaires d'une même fiche sont possibles.",
        },
    )


@require_POST
def archive(request: HttpRequest, copy_id: UUID) -> HttpResponse:
    try:
        services.archive(actor(request), copy_id)
    except ValidationError as error:
        return render(
            request, "domain_error.html", {"message": " ".join(error.messages)}, status=400
        )
    return redirect("inventory:mine")
