from django import forms

from muqola.communities.models import Community


class CommunityForm(forms.Form):
    illustration = forms.ChoiceField(
        label="Illustration",
        choices=Community.Illustration.choices,
        required=False,
        initial="table",
    )

    def clean_illustration(self) -> str:
        return str(self.cleaned_data["illustration"] or "table")

    name = forms.CharField(label="Nom de la communauté", max_length=100)
    description = forms.CharField(
        label="Description", max_length=1000, required=False, widget=forms.Textarea
    )


class InviteForm(forms.Form):
    days = forms.IntegerField(
        label="Expiration facultative (jours)",
        min_value=1,
        max_value=30,
        required=False,
        help_text="Laissez vide pour un lien permanent.",
    )
