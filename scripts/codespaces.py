"""Démarrage du profil Codespaces ; fermeture si la confidentialité est invérifiable."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from config.codespaces_environment import origins

ROOT = Path(__file__).resolve().parent.parent
PORTS = {8000, 8025}


def require_private_ports(ports: list[dict[str, object]]) -> None:
    seen = {port.get("sourcePort"): port.get("visibility") for port in ports}
    if any(seen.get(number) != "private" for number in PORTS):
        raise RuntimeError("Les ports 8000 et 8025 doivent être privés ; démarrage refusé.")
    # Ne pas laisser de transfert antérieur de PostgreSQL/SMTP dans ce Codespace.
    if any(port.get("sourcePort") not in PORTS for port in ports):
        raise RuntimeError("Retirez les autres ports transférés dans Ports, puis réessayez.")


def github(arguments: list[str]) -> str:
    environments = [
        dict(os.environ),
        {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN"}},
    ]
    binary = shutil.which("gh")
    if binary is None:
        raise RuntimeError("GitHub CLI (gh) est requis pour contrôler les ports privés.")
    for environment in environments:
        result = subprocess.run(  # noqa: S603
            [binary, "codespace", "ports", *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=70,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    raise RuntimeError(
        "Impossible de vérifier les ports GitHub. Dans Ports, ajoutez 8000 et 8025 "
        "en Private. Si l'authentification est demandée, exécutez : "
        "env -u GH_TOKEN -u GITHUB_TOKEN gh auth login --web --scopes codespace ; "
        "puis relancez bash .devcontainer/start.sh. Aucun service de test n'a été démarré."
    )


def main() -> int:
    application, mailpit = origins(os.environ)
    os.chdir(ROOT)
    (ROOT / "work").mkdir(exist_ok=True)
    with (ROOT / "work/codespaces-start.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        subprocess.run([sys.executable, "scripts/init_dev.py"], check=True)  # noqa: S603
        compose = [
            "docker",
            "compose",
            "--project-name",
            "muqola-codespaces",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(ROOT / ".devcontainer/compose.codespaces.yaml"),
        ]
        # Les conteneurs ne redémarrent pas seuls. Une réouverture d'éditeur
        # ne doit pas arrêter Mailpit et effacer ses e-mails de test.
        name = os.environ["CODESPACE_NAME"]
        try:
            github(["visibility", "8000:private", "8025:private", "-c", name])
            ports = json.loads(github(["--json", "sourcePort,visibility", "-c", name]))
            require_private_ports(ports)
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            subprocess.run([*compose, "stop", "web", "worker", "mailpit"], check=True)  # noqa: S603
            raise
        subprocess.run([*compose, "build", "web"], check=True)  # noqa: S603
        subprocess.run(  # noqa: S603
            [*compose, "up", "--no-build", "--wait", "--wait-timeout", "120"], check=True
        )
        print("Muqola prête — accès privé avec votre compte GitHub.")
        print(f"Application : {application}")
        print(f"E-mails de test : {mailpit}")
        print("Utilisez exclusivement des adresses fictives @example.test.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
