from typing import Any

from django import forms

from muqola.communities.models import Membership
from muqola.identity.models import User


class CopyForm(forms.Form):
    notes = forms.CharField(
        label="État et commentaires de mon exemplaire",
        max_length=500,
        required=False,
        widget=forms.Textarea,
    )
    communities = forms.TypedMultipleChoiceField(
        label="Communautés de partage (facultatif)",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    withdrawn = forms.BooleanField(label="Retiré du prêt", required=False)

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["communities"].choices = [  # type: ignore[attr-defined]
            (str(m.community_id), m.community.name)
            for m in Membership.objects.filter(user=user, active=True).select_related("community")
        ]


class SearchForm(forms.Form):
    title = forms.CharField(label="Titre", max_length=120, required=False)
    community = forms.ChoiceField(label="Communauté", required=False)
    players = forms.IntegerField(
        label="Nombre de joueurs", min_value=1, max_value=100, required=False
    )
    only_available = forms.BooleanField(label="Disponibles uniquement", required=False)

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["community"].choices = [("", "Toutes mes communautés")] + [  # type: ignore[attr-defined]
            (str(m.community_id), m.community.name)
            for m in Membership.objects.filter(user=user, active=True).select_related("community")
        ]
