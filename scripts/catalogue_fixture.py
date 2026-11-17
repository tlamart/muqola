"""Local synthetic browser fixtures; never run against production or import a CSV."""

import json
import secrets
import shutil
import subprocess
from urllib.parse import urlsplit
from uuid import UUID


def local_command(*args: str, content: str | None = None) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker local est nécessaire au parcours de modération.")
    result = subprocess.run(  # noqa: S603 — fixed local Compose, argument array, no shell.
        [docker, "compose", "exec", "-T", "web", "python", "manage.py", *args],
        input=content,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def approve_proposal(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("Fixtures réservées à une pile locale jetable.")
    game_id = str(UUID(parsed.path.strip("/").split("/")[-1]))
    email = "catalogue-smoke-" + secrets.token_hex(6) + "@example.test"
    # This existing command rejects non-development configurations and real addresses.
    local_command("create_dev_operator", "--email", email)
    local_command(
        "ops",
        "approve-game",
        "--operator",
        email,
        "--game-id",
        game_id,
        "--reason",
        "Revue synthétique du parcours navigateur",
        "--homonym-reason",
        "Jeux synthétiques distincts pour le parcours",
        "--metadata-file",
        "/dev/stdin",
        content=json.dumps({"kind": "standalone"}),
    )


def commons_fixture() -> None:
    # Static synthetic content only. No supplied catalogue, user data or network request.
    local_command(
        "shell",
        "-c",
        """
from django.conf import settings
from django.utils import timezone
from muqola.identity.models import User
from muqola.catalogue.models import GameIllustration
from muqola.catalogue.services import write_game
from muqola.catalogue.moderation import decide
assert settings.APP_ENV == 'development'
u = User.objects.create(
 email='commons-fixture-' + __import__('uuid').uuid4().hex + '@example.test',
 display_name='Fixture synthétique', password='!', is_superuser=True,
 email_verified_at=timezone.now(), adult_confirmed_at=timezone.now())
g = write_game(u, {'title':'Les Pions du Canal fictifs',
 'aliases':['Fictional Canal Tokens'], 'proposal_reason':'Fixture synthétique'})
g = decide(u, g.pk, 'approved', 'Revue synthétique', {'kind':'standalone'},
 'Fixture synthétique distincte')
g.data_source='Wikidata'
g.data_license='CC0'
g.save()
i=GameIllustration(game=g,
 image_url='https://commons.wikimedia.org/wiki/Special:FilePath/Synthetic_game.jpg',
 commons_file='File:Synthetic game.jpg',
 source_url='https://commons.wikimedia.org/wiki/File:Synthetic_game.jpg',
 license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0',
 artist='Auteur fictif',attribution='Photographie synthétique')
i.full_clean()
i.save()
""",
    )


if __name__ == "__main__":
    commons_fixture()
