"""Origines exactes du seul profil de développement GitHub Codespaces."""

import re
from collections.abc import Mapping


def origins(environment: Mapping[str, str]) -> tuple[str, str]:
    if environment.get("CODESPACES") != "true":
        raise ValueError("Ce profil est réservé à GitHub Codespaces.")
    if environment.get("APP_ENV", "development") != "development":
        raise ValueError("Le profil Codespaces ne peut pas être utilisé en production ou en test.")
    name = environment.get("CODESPACE_NAME", "")
    domain = environment.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?", name):
        raise ValueError("CODESPACE_NAME doit être un nom DNS Codespaces valide.")
    if domain != "app.github.dev":
        raise ValueError("Seul le domaine de prévisualisation GitHub app.github.dev est autorisé.")
    return f"https://{name}-8000.{domain}", f"https://{name}-8025.{domain}"
