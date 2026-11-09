from django import forms


class CommunityForm(forms.Form):
    name = forms.CharField(label="Nom de la communauté", max_length=100)
    description = forms.CharField(
        label="Description", max_length=1000, required=False, widget=forms.Textarea
    )


class InviteForm(forms.Form):
    days = forms.IntegerField(label="Durée du lien (jours)", min_value=1, max_value=30, initial=7)
