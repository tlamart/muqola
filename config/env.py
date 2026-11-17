"""Read deployment secrets from mounted files without putting them in errors."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def secret(name: str, default: str = "") -> str:
    direct, filename = os.environ.get(name), os.environ.get(name + "_FILE")
    if direct is not None and filename:
        raise ImproperlyConfigured(f"Choisir {name} ou {name}_FILE, pas les deux.")
    if filename:
        try:
            path = Path(filename)
            if path.stat().st_size > 16384:
                raise ValueError
            return path.read_text().rstrip("\r\n")
        except (OSError, UnicodeError, ValueError) as error:
            raise ImproperlyConfigured(f"Secret {name} indisponible.") from error
    return direct if direct is not None else default
