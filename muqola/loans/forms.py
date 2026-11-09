from datetime import timedelta
from typing import Any

from django import forms

from muqola.loans.services import today


class RequestForm(forms.Form):
    due_date = forms.DateField(
        label="Date de retour souhaitée (obligatoire)",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    message = forms.CharField(
        label="Message (facultatif)", max_length=500, required=False, widget=forms.Textarea
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["due_date"].widget.attrs["min"] = (today() + timedelta(days=1)).isoformat()
