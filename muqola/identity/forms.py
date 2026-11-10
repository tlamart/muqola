from typing import Any

from django import forms
from django.contrib.auth.password_validation import validate_password

from muqola.identity.models import User


class EmailForm(forms.Form):
    email = forms.EmailField(
        label="Adresse e-mail",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def clean_email(self) -> str:
        return str(self.cleaned_data["email"]).strip().lower()


class LoginForm(EmailForm):
    password = forms.CharField(
        label="Mot de passe",
        strip=False,
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class PasswordForm(forms.Form):
    password = forms.CharField(
        label="Mot de passe",
        strip=False,
        min_length=12,
        max_length=128,
        help_text="12 caractères minimum. Évitez les mots de passe courants.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        strip=False,
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args: Any, user: User | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if data.get("password") and data.get("password_confirm"):
            if data["password"] != data["password_confirm"]:
                self.add_error("password_confirm", "Les mots de passe ne correspondent pas.")
            user = self.user or User(
                email=data.get("email", ""), display_name=data.get("display_name", "")
            )
            validate_password(data["password"], user=user)
        return data


class SignupForm(EmailForm, PasswordForm):
    display_name = forms.CharField(
        label="Nom d'affichage",
        max_length=80,
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    field_order = ["display_name", "email", "password", "password_confirm"]
