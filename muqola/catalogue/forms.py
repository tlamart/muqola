from typing import TYPE_CHECKING

from django import forms

from muqola.catalogue.models import Game

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
