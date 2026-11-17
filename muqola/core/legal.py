"""Operator-reviewed plain text; never publish placeholder legal identities."""

from django.conf import settings

DOCUMENTS = {
    "mentions": ("Mentions légales", "mentions.txt"),
    "terms": ("Conditions générales d’utilisation — 18 ans et plus", "terms.txt"),
    "privacy": ("Politique de confidentialité", "privacy.txt"),
    "support": ("Contact, support et suppression de compte", "support.txt"),
}
MARKERS = ("[À RENSEIGNER", "[A RENSEIGNER", "[À COMPLÉTER", "[A COMPLETER", "{{", "REPLACE_WITH")


def documents() -> dict[str, str]:
    if not settings.LEGAL_REVIEWED:
        return {}
    result = {}
    try:
        for key, (_, filename) in DOCUMENTS.items():
            path = settings.LEGAL_DOCUMENTS_DIR / filename
            if path.stat().st_size > 131072:
                return {}
            content = path.read_text().strip()
            if not content or any(marker in content.upper() for marker in MARKERS):
                return {}
            result[key] = content
    except (OSError, UnicodeError):
        return {}
    return result
