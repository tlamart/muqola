from uuid import UUID

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from muqola.core.http import actor
from muqola.identity.ratelimit import allowed
from muqola.identity.views import throttled
from muqola.inventory.services import visible
from muqola.loans import services
from muqola.loans.forms import RequestForm
from muqola.loans.models import Loan


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "loans/index.html",
        {
            "loans": Paginator(services.participant_loans(actor(request)), 30).get_page(
                request.GET.get("page")
            )
        },
    )


@require_http_methods(["GET", "POST"])
def request_loan(request: HttpRequest, copy_id: UUID) -> HttpResponse:
    item = get_object_or_404(visible(actor(request)), pk=copy_id)
    form = RequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not allowed(request, "loan", actor(request).email):
            return throttled(request, "loan")
        try:
            loan = services.request_loan(actor(request), copy_id, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Demande envoyée. Elle ne réserve pas le jeu.")
            return redirect("loans:detail", loan_id=loan.pk)
    return render(
        request,
        "domain_form.html",
        {
            "form": form,
            "title": f"Demander {item.game.title}",
            "submit": "Envoyer ma demande",
            "notice": "Une demande ne réserve pas le jeu. Après acceptation, vos adresses e-mail "
            "vérifiées seront partagées pendant le prêt actif. "
            "Une adresse déjà communiquée ne peut pas être reprise.",
        },
    )


@require_GET
def detail(request: HttpRequest, loan_id: UUID) -> HttpResponse:
    loan = get_object_or_404(services.participant_loans(actor(request)), pk=loan_id)
    # Présentation fermée : aucun objet User ni e-mail dans les états clos.
    return render(
        request,
        "loans/detail.html",
        {
            "loan_id": loan.pk,
            "title": loan.owned_game.game.title,
            "state": loan.state,
            "state_label": loan.get_state_display(),
            "due_date": loan.due_date,
            "message": loan.message,
            "reason": loan.close_reason,
            "owner_name": loan.owner.display_name,
            "borrower_name": loan.borrower.display_name,
            "is_owner": loan.owner_id == actor(request).pk,
            "contacts": services.contacts(actor(request), loan.pk),
            "events": [
                {
                    "state": Loan.State(e.state).label,
                    "created_at": e.created_at,
                    "reason": e.reason,
                    "administrative": e.administrative,
                }
                for e in loan.events.all()
            ],
        },
    )


@require_POST
def action(request: HttpRequest, loan_id: UUID, action: str) -> HttpResponse:
    try:
        services.transition(actor(request), loan_id, action)
        messages.success(request, "Le prêt a été mis à jour.")
    except ValidationError as error:
        return render(
            request, "domain_error.html", {"message": " ".join(error.messages)}, status=400
        )
    return redirect("loans:detail", loan_id=loan_id)
