from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from muqola.core.http import actor
from muqola.loans.models import Loan
from muqola.operations.models import DeletionRequest
from muqola.operations.services import request_deletion


class DeletionForm(forms.Form):
    reason = forms.CharField(
        label="Précision (facultatif, sans donnée sensible)",
        max_length=500,
        required=False,
        widget=forms.Textarea,
    )
    confirm = forms.BooleanField(label="Je confirme demander la suppression de mon compte.")


@require_http_methods(["GET", "POST"])
def profile(request: HttpRequest) -> HttpResponse:
    user = actor(request)
    form = DeletionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        request_deletion(user, form.cleaned_data["reason"])
        messages.success(request, "Votre demande de suppression est enregistrée pour traitement.")
        return redirect("identity:profile")
    active = (
        Loan.objects.filter(owner=user, state__in=["ACCEPTED", "HANDED_OVER"]).exists()
        or Loan.objects.filter(borrower=user, state__in=["ACCEPTED", "HANDED_OVER"]).exists()
    )
    return render(
        request,
        "identity/profile.html",
        {
            "form": form,
            "deletion": DeletionRequest.objects.filter(user=user).first(),
            "active_loans": active,
        },
    )
