"""Ajout rapide réel avec/sans JS ; comptes fictifs et Mailpit local uniquement.

Une recherche existante est requise (--title), importée localement ou créée par
product_browser_smoke.py en CI. Aucune donnée externe embarquée dans ce script.
"""

import argparse
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
parser.add_argument("--title", default="Jeu scénario")
args = parser.parse_args()
if any(
    urlparse(url).hostname not in {"localhost", "127.0.0.1"}
    or urlparse(url).scheme not in {"http", "https"}
    for url in (args.url, args.mailpit)
):
    raise RuntimeError("Ce smoke test est réservé à une pile locale jetable.")
output = Path("work/catalogue-quick-add")
output.mkdir(parents=True, exist_ok=True)
email = "quick-" + secrets.token_hex(8) + "@example.test"
password = secrets.token_urlsafe(24)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    context = browser.new_context()
    page = context.new_page()
    page.goto(args.url + "/accounts/signup/")
    page.get_by_label("Nom d'affichage").fill("Collection fictive")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.locator("input[name=password_confirm]").fill(password)
    page.get_by_role("button", name="S'inscrire", exact=True).click()
    page.wait_for_url("**/accounts/signup/done/")
    link = ""
    for _ in range(30):
        with urlopen(args.mailpit + "/api/v1/messages", timeout=5) as response:  # noqa: S310
            messages = json.load(response)["messages"]
        for message in messages:
            if any(to["Address"] == email for to in message["To"]):
                with urlopen(  # noqa: S310 — URL locale validée ci-dessus.
                    args.mailpit + "/api/v1/message/" + message["ID"], timeout=5
                ) as response:  # noqa: S310
                    match = re.search(
                        r"http[^\s]+/accounts/verify/[A-Za-z0-9_-]{43}/",
                        json.load(response)["Text"],
                    )
                if match:
                    link = match.group(0)
        if link:
            break
        time.sleep(1)
    if not link:
        raise RuntimeError("Lien de vérification absent de Mailpit")
    page.goto(link)
    page.get_by_role("button", name="Confirmer mon e-mail", exact=True).click()
    page.wait_for_url("**/accounts/verify/done/")
    page.goto(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.wait_for_url("**/accounts/dashboard/")
    community_names = [
        "Groupe fictif A " + secrets.token_hex(3),
        "Groupe fictif B " + secrets.token_hex(3),
    ]
    for name in community_names:
        page.goto(args.url + "/communities/")
        page.get_by_label("Nom de la communauté").fill(name)
        page.get_by_role("button", name="Créer ma communauté", exact=True).click()
        page.wait_for_url("**/communities/*/")
    state = context.storage_state()
    context.close()
    for javascript in (True, False):
        for width in (360, 768, 1280):
            ctx = browser.new_context(
                storage_state=state,
                java_script_enabled=javascript,
                viewport={"width": width, "height": 900},
            )
            page = ctx.new_page()
            external: list[str] = []
            page.on(
                "request",
                lambda request, external=external: (
                    external.append(request.url) if "boardgamegeek" in request.url.lower() else None
                ),
            )
            page.goto(args.url + "/games/")
            page.get_by_label("Rechercher un jeu par titre", exact=True).fill(args.title)
            page.get_by_role("button", name="Rechercher", exact=True).click()
            choice = page.locator("input[name=game_id]").first
            expect(choice).to_be_visible()
            choice.focus()
            page.keyboard.press("Space")
            expect(choice).to_be_checked()
            page.get_by_label("État et commentaires de mon exemplaire").fill(
                "Ajout rapide synthétique"
            )
            if width != 360:
                for name in community_names:
                    page.get_by_label(name, exact=True).check()
            if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                raise RuntimeError("Débordement horizontal de l'ajout rapide")
            page.screenshot(
                path=str(output / f"select-{width}-js-{javascript}.png"), full_page=True
            )
            page.get_by_role("button", name="Ajouter à ma collection", exact=True).click()
            page.wait_for_url("**/copies/*/")
            expect(page.locator("main")).to_contain_text("Ajout rapide synthétique")
            if width == 360:
                expect(page.locator("main")).to_contain_text("Aucune communauté")
            else:
                for name in community_names:
                    expect(page.locator("main")).to_contain_text(name)
            manual = "Jeu absent fictif " + secrets.token_hex(5)
            page.goto(args.url + "/games/")
            page.get_by_label("Rechercher un jeu par titre", exact=True).fill(manual)
            page.get_by_role("button", name="Rechercher", exact=True).click()
            page.get_by_role("link", name="Mon jeu n’est pas dans la liste", exact=True).click()
            expect(page.get_by_label("Titre du jeu")).to_have_value(manual)
            page.get_by_role("button", name="Créer ce jeu et l’ajouter", exact=True).click()
            page.wait_for_url("**/copies/*/")
            expect(page.get_by_role("heading", level=1)).to_have_text(manual)
            if external:
                raise RuntimeError("Appel BGG inattendu")
            ctx.close()
            print(
                f"PASS ajout rapide {width}px JS={javascript}: sélection clavier, "
                "privé/partagé, création manuelle, aucun appel BGG",
                flush=True,
            )
    browser.close()
