"""AdminSite deliberately exposing only catalogue review, never generic model writes."""

from typing import Any, cast
from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.admin import AdminSite
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_http_methods

from muqola.catalogue import moderation
from muqola.catalogue.models import Game
from muqola.catalogue.services import FIELDS
from muqola.core.http import actor
from muqola.core.transactions import domain_write
from muqola.identity.models import User
from muqola.identity.ratelimit import allowed
from muqola.identity.views import sign_out, throttled
from muqola.operations.services import operator


class DecisionForm(forms.Form):
    revision = forms.CharField(widget=forms.HiddenInput)
    status = forms.ChoiceField(
        label="Décision",
        choices=[
            (Game.Status.APPROVED, "Approuver"),
            (Game.Status.PENDING, "Demander des corrections / réexaminer"),
            (Game.Status.REJECTED, "Rejeter"),
        ],
    )
    reason = forms.CharField(
        label="Motif de la décision (sans données sensibles)", max_length=500, widget=forms.Textarea
    )
    homonym_reason = forms.CharField(
        label="Justification d’une homonymie réelle",
        max_length=500,
        required=False,
        widget=forms.Textarea,
    )
    title = forms.CharField(label="Titre du jeu", max_length=120)
    kind = forms.ChoiceField(label="Type de jeu", choices=Game.Kind.choices)
    base_game_id = forms.ModelChoiceField(
        label="Jeu de base nécessaire", required=False, queryset=Game.objects.none()
    )
    publisher = forms.CharField(label="Éditeur", max_length=120, required=False)
    year = forms.IntegerField(label="Année", required=False)
    players_min = forms.IntegerField(label="Joueurs minimum", required=False)
    players_max = forms.IntegerField(label="Joueurs maximum", required=False)
    duration = forms.IntegerField(label="Durée (minutes)", required=False)
    description = forms.CharField(
        label="Description", max_length=2000, required=False, widget=forms.Textarea
    )
    aliases = forms.CharField(
        label="Titres alternatifs à ajouter (un par ligne)",
        max_length=2400,
        required=False,
        widget=forms.Textarea,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast(
            "forms.ModelChoiceField[Game]", self.fields["base_game_id"]
        ).queryset = Game.objects.filter(
            moderation_status=Game.Status.APPROVED, hidden=False, merged_into__isnull=True
        ).order_by("title", "id")


def revision(game: Game) -> str:
    decision = game.decisions.values_list("pk", flat=True).first()
    return f"{game.updated_at.isoformat()}:{decision}"


class CatalogueAdminSite(AdminSite):
    site_header = "Modération du catalogue"

    def has_permission(self, request: HttpRequest) -> bool:
        return (
            request.user.is_authenticated
            and User.objects.filter(
                pk=request.user.pk,
                is_active=True,
                is_staff=True,
                is_superuser=True,
                email_verified_at__isnull=False,
                adult_confirmed_at__isnull=False,
            ).exists()
        )

    def authorize(self, request: HttpRequest) -> None:
        if not self.has_permission(request):
            raise PermissionDenied
        operator(actor(request))

    def get_urls(self) -> list[Any]:
        # No default model routes, user/group management, bulk actions or admin login form.
        return [
            path("", self.admin_view(self.index), name="index"),
            path("login/", self.login, name="login"),
            path("logout/", sign_out, name="logout"),
            path("games/<uuid:game_id>/", self.admin_view(self.review), name="review"),
        ]

    @method_decorator(require_GET)
    def login(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        if request.user.is_authenticated:
            self.authorize(request)
            return redirect("catalogue_admin:index")
        return redirect("identity:login")

    @method_decorator(require_GET)
    def index(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> TemplateResponse:
        self.authorize(request)
        status = request.GET.get("status", "review")
        query = Game.objects.filter(merged_into__isnull=True).order_by("created_at", "id")
        if status in Game.Status.values:
            query = query.filter(moderation_status=status)
        else:
            status = "review"
            query = query.filter(moderation_status__in=[Game.Status.PENDING, Game.Status.LEGACY])
        title = request.GET.get("q", "")[:120].strip()
        if title:
            query = query.filter(
                Q(title__icontains=title) | Q(aliases__title__icontains=title)
            ).distinct()
        page = Paginator(query, 30).get_page(request.GET.get("page"))
        return TemplateResponse(
            request,
            "operations/catalogue_index.html",
            {
                "page": page,
                "statuses": Game.Status.choices,
                "selected_status": status,
                "q": title,
            },
        )

    @method_decorator(require_http_methods(["GET", "POST"]))
    def review(self, request: HttpRequest, game_id: UUID) -> HttpResponse:
        self.authorize(request)
        game = get_object_or_404(Game, pk=game_id, merged_into__isnull=True)
        initial = {field: getattr(game, field) for field in FIELDS}
        initial.update(
            status=Game.Status.APPROVED,
            revision=signing.dumps(
                {"id": str(game.pk), "revision": revision(game)}, salt="catalogue-review"
            ),
        )
        form = DecisionForm(request.POST if request.method == "POST" else None, initial=initial)
        response_status = 200
        if request.method == "POST":
            if not allowed(request, "moderation", actor(request).email):
                return throttled(request, "moderation")
            if form.is_valid():
                try:
                    if set(request.POST) - set(form.fields) - {"csrfmiddlewaretoken"}:
                        raise ValidationError("Champs non autorisés dans la décision.")
                    payload = signing.loads(
                        form.cleaned_data["revision"], salt="catalogue-review", max_age=3600
                    )
                    with domain_write(actor(request)):
                        self.authorize(request)
                        game.refresh_from_db()
                        if payload != {"id": str(game.pk), "revision": revision(game)}:
                            raise ValidationError(
                                "La fiche a changé. Rechargez la page et refaites la revue."
                            )
                        metadata = {field: form.cleaned_data[field] for field in FIELDS}
                        base = form.cleaned_data["base_game_id"]
                        metadata["base_game_id"] = base.pk if base else None
                        metadata["aliases"] = form.cleaned_data["aliases"].splitlines()
                        moderation.decide(
                            actor(request),
                            game.pk,
                            form.cleaned_data["status"],
                            form.cleaned_data["reason"],
                            metadata,
                            form.cleaned_data["homonym_reason"],
                        )
                except (ValidationError, signing.BadSignature) as error:
                    text = "Formulaire expiré. Rechargez la page."
                    if isinstance(error, ValidationError):
                        text = " ".join(error.messages)
                    game.refresh_from_db()
                    form.add_error(None, text)
                    response_status = 400
                else:
                    messages.success(request, "Décision enregistrée dans le journal de modération.")
                    return redirect("catalogue_admin:review", game_id=game.pk)
            else:
                response_status = 400
        return render(
            request,
            "operations/catalogue_review.html",
            {
                "game": game,
                "form": form,
                "decisions": game.decisions.select_related("actor")[:30],
                "duplicates": moderation.duplicates(game).order_by("title", "id")[:20],
                "similar": moderation.similar(game)[:20],
            },
            status=response_status,
        )


catalogue_admin = CatalogueAdminSite(name="catalogue_admin")
