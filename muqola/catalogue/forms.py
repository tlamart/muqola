from typing import TYPE_CHECKING, Any

from django import forms

from muqola.catalogue.models import Game
from muqola.inventory.forms import CopyForm

if TYPE_CHECKING:
    GameModelForm = forms.ModelForm[Game]
else:
    GameModelForm = forms.ModelForm


class GameForm(GameModelForm):
    class Meta:
        model = Game
        fields = [
            "title",
            "publisher",
            "year",
            "players_min",
            "players_max",
            "duration",
            "description",
        ]
        labels = {
            "title": "Titre du jeu",
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
    distinct_edition = forms.BooleanField(
        label="Il s'agit d'un autre jeu ou d'une autre édition", required=False
    )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if not data.get("game_id") and not data.get("title"):
            raise forms.ValidationError("Sélectionnez un jeu ou indiquez le titre du jeu absent.")
        if data.get("game_id") and data.get("title"):
            raise forms.ValidationError("Choisissez un jeu existant ou un nouveau titre.")
        return data
