"""Validation locale des seules références Commons autorisées ; aucun accès réseau."""

import re
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ValidationError


def allowed_url(value: str, host: str, prefix: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError as error:
        raise ValidationError("URL invalide.") from error
    if (
        parts.scheme != "https"
        or parts.netloc != host
        or not parts.path.startswith(prefix)
        or parts.query
        or parts.fragment
        or any(c.isspace() or ord(c) < 32 for c in value)
        or "\\" in value
    ):
        raise ValidationError("URL HTTPS autorisée uniquement.")
    return unquote(parts.path[len(prefix) :]).replace("_", " ")


def license_url(value: str) -> str:
    # Les anciens liens CC du fichier sont équivalents en HTTPS ; pas de requête.
    if value.startswith("http://creativecommons.org/"):
        value = "https://" + value.removeprefix("http://")
    return value


def validate_illustration(
    image_url: str,
    commons_file: str,
    source_url: str,
    license_name: str,
    license_link: str,
    artist: str,
    attribution: str,
    review_status: str,
) -> None:
    if review_status != "approved_by_owner":
        raise ValidationError("Illustration non approuvée.")
    filename = commons_file.removeprefix("File:").replace("_", " ")
    if not commons_file.startswith("File:") or not filename or any(ord(c) < 32 for c in filename):
        raise ValidationError("Nom de fichier Commons invalide.")
    image_file = allowed_url(image_url, "commons.wikimedia.org", "/wiki/Special:FilePath/")
    source_file = allowed_url(source_url, "commons.wikimedia.org", "/wiki/File:")
    if image_file != filename or source_file != filename:
        raise ValidationError("Les trois références doivent désigner le même fichier Commons.")
    path = allowed_url(license_link, "creativecommons.org", "/")
    if license_name == "CC0":
        expected = "publicdomain/zero/1.0"
    else:
        match = re.fullmatch(r"CC (BY(?:-SA)?) (1\.0|2\.0|2\.5|3\.0|4\.0)", license_name)
        if match is None:
            raise ValidationError("Licence d'illustration non prise en charge.")
        expected = f"licenses/{match[1].lower()}/{match[2]}"
        if not (artist or attribution):
            raise ValidationError("Auteur ou attribution obligatoire pour CC BY et CC BY-SA.")
    if re.fullmatch(re.escape(expected) + r"(?:/(?:deed\.[a-zA-Z-]+|legalcode))?/?", path) is None:
        raise ValidationError("Le lien de licence ne correspond pas à la licence annoncée.")
