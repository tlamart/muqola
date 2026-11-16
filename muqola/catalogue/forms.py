from typing import TYPE_CHECKING, Any, cast

from django import forms

from muqola.catalogue.models import Game
from muqola.inventory.forms import CopyForm

if TYPE_CHECKING:
    GameModelForm = forms.ModelForm[Game]
else:
    GameModelForm = forms.ModelForm


class GameForm(GameModelForm):
    kind = forms.ChoiceField(label="Type de jeu", choices=Game.Kind, required=False)
    alternate_titles = forms.CharField(
        label="Titres alternatifs (un par ligne)",
        required=False,
        max_length=2400,
        widget=forms.Textarea,
    )
    proposal_reason = forms.CharField(
        label="Pourquoi un jeu distinct ? (si un titre existe déjà, pas une autre édition)",
        required=False,
        max_length=500,
        widget=forms.Textarea,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast(
            "forms.ModelChoiceField[Game]", self.fields["base_game"]
        ).queryset = Game.objects.filter(
            moderation_status=Game.Status.APPROVED, hidden=False, merged_into__isnull=True
        )

    def clean_kind(self) -> str:
        return str(self.cleaned_data.get("kind") or Game.Kind.UNKNOWN)

    class Meta:
        model = Game
        fields = [
            "title",
            "kind",
            "base_game",
            "proposal_reason",
            "publisher",
            "year",
            "players_min",
            "players_max",
            "duration",
            "description",
        ]
        labels = {
            "title": "Titre du jeu",
            "base_game": "Jeu de base nécessaire",
            "publisher": "Éditeur",
            "year": "Année",
            "players_min": "Joueurs minimum",
            "players_max": "Joueurs maximum",
            "duration": "Durée (minutes)",
            "description": "Description générique",
        }
        widgets = {"description": forms.Textarea}


class ReportForm(forms.Form):
    reason = forms.CharField(
        label="Correction ou signalement (sans données personnelles)",
        max_length=1000,
        widget=forms.Textarea,
    )


class QuickAddForm(CopyForm):
    game_id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    title = forms.CharField(label="Titre du jeu", max_length=120, required=False)
    proposal_reason = forms.CharField(
        label="Pourquoi un jeu distinct ? (pas une autre édition)",
        max_length=500,
        required=False,
        widget=forms.Textarea,
    )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if not data.get("game_id") and not data.get("title"):
            raise forms.ValidationError("Sélectionnez un jeu ou indiquez le titre du jeu absent.")
        if data.get("game_id") and data.get("title"):
            raise forms.ValidationError("Choisissez un jeu existant ou un nouveau titre.")
        return data
