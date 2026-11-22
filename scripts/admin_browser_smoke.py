"""Catalogue admin journey on a disposable local Compose stack only."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--browser", default="/usr/bin/chromium")
args = parser.parse_args()
if urlsplit(args.url).hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("Pile locale jetable uniquement.")
# The fixture refuses production before writing anything; no password is printed.
fixture = """
import json, secrets
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from muqola.identity.models import User
from muqola.catalogue.services import write_game
if settings.APP_ENV != 'development' or settings.DEPLOYMENT_ENV != 'development':
    raise RuntimeError('Development fixture only')
email = 'admin-smoke-' + secrets.token_hex(8) + '@example.test'
password = secrets.token_urlsafe(32)
user = User.objects.create_user(email, password, display_name='Revue synthétique',
    email_verified_at=timezone.now(), adult_confirmed_at=timezone.now())
existing = User.objects.filter(is_superuser=True, is_active=True,
    email_verified_at__isnull=False, adult_confirmed_at__isnull=False).first()
from io import StringIO
mode = {'operator': existing.email} if existing else {'bootstrap': True}
call_command('promote_operator', email=email, confirm_email=email,
    reason='Fixture de test navigateur locale', stdout=StringIO(), **mode)
game = write_game(user, {'title': 'Proposition admin ' + secrets.token_hex(4)})
print(json.dumps({'email': email, 'password': password, 'game': str(game.pk), 'title': game.title}))
"""
docker = shutil.which("docker")
if docker is None:
    raise RuntimeError("Docker requis pour la fixture locale")
result = subprocess.run(  # noqa: S603
    [docker, "compose", "exec", "-T", "web", "python", "manage.py", "shell", "-c", fixture],
    check=True,
    capture_output=True,
    text=True,
)
account = json.loads(result.stdout.strip().splitlines()[-1])
output = Path("work/admin-smoke")
output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    context = browser.new_context(viewport={"width": 360, "height": 900}, java_script_enabled=False)
    page = context.new_page()
    failures: list[str] = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(args.url + "/operator/")
    expect(page).to_have_url(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(account["email"])
    page.locator("input[name=password]").fill(account["password"])
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.wait_for_url("**/accounts/dashboard/")
    page.goto(args.url + "/operator/games/" + account["game"] + "/")
    for status, reason in [
        ("pending", "Précisez le type"),
        ("rejected", "Doublon à revoir"),
        ("approved", "Type et doublons vérifiés"),
    ]:
        page.locator("select[name=status]").select_option(status)
        page.get_by_label("Motif de la décision (sans données sensibles)").fill(reason)
        if status == "approved":
            page.get_by_label("Type de jeu").select_option("standalone")
        page.get_by_role("button", name="Confirmer la décision", exact=True).click()
        expect(
            page.get_by_text("Décision enregistrée dans le journal de modération.", exact=True)
        ).to_be_visible()
        expect(page.locator("ol")).to_contain_text(reason)
    for width in (360, 768, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
            raise RuntimeError("Débordement dans la revue opérateur")
        page.screenshot(path=str(output / f"review-{width}.png"), full_page=True)
    page.goto(args.url + "/operator/")
    page.get_by_label("Statut", exact=True).select_option("approved")
    page.get_by_label("Titre ou alias", exact=True).fill(account["title"])
    page.get_by_role("button", name="Filtrer", exact=True).click()
    expect(page.get_by_role("link", name=account["title"], exact=True)).to_be_visible()
    assert not failures  # noqa: S101
    browser.close()
print(
    "PASS administration : promotion auditée, connexion normale, "
    "trois décisions et trois largeurs sans JS"
)
