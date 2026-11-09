"""Génère uniquement des secrets locaux, sans écraser un .env existant."""

import os
import secrets
from pathlib import Path

path = Path(".env")
content = Path(".env.example").read_text()
content = content.replace(
    "CHANGE_ME_GENERATE_AT_LEAST_50_RANDOM_CHARACTERS", secrets.token_urlsafe(64)
)
content = content.replace("CHANGE_ME_LOCAL_RANDOM_PASSWORD", secrets.token_urlsafe(32))
try:
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(content)
except FileExistsError:
    print(".env existe déjà : conservé.")
else:
    print(".env local créé (0600), sans affichage des secrets.")
