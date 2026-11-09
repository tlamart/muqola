"""Parcours produit réel, données fictives, SMTP capturé localement."""

import argparse
import json
import re
import secrets
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Browser, Page, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
args = parser.parse_args()
Path("work").mkdir(exist_ok=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verification_link(email: str) -> str:
    for _ in range(30):
        with urlopen(args.mailpit + "/api/v1/messages", timeout=5) as response:  # noqa: S310
            messages = json.load(response)["messages"]
        for item in messages:
            if any(to["Address"] == email for to in item["To"]):
                with urlopen(args.mailpit + "/api/v1/message/" + item["ID"], timeout=5) as response:  # noqa: S310
                    body = json.load(response)["Text"]
                match = re.search(r"http[^\s]+/accounts/verify/[A-Za-z0-9_-]{43}/", body)
                if match:
                    return match.group(0)
        time.sleep(1)
    raise RuntimeError("E-mail de vérification absent de la capture")


def register(browser: Browser, page: Page, name: str) -> None:
    email = "scenario-" + secrets.token_hex(6) + "@example.test"
    password = secrets.token_urlsafe(24)
    page.goto(args.url + "/accounts/signup/")
    page.get_by_label("Nom d'affichage").fill(name)
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.locator("input[name=password_confirm]").fill(password)
    page.get_by_role("button", name="S'inscrire", exact=True).click()
    page.wait_for_url("**/accounts/signup/done/")
    context = browser.new_context()
    confirmation = context.new_page()
    confirmation.goto(verification_link(email))
    confirmation.get_by_role("button", name="Confirmer mon e-mail", exact=True).click()
    confirmation.wait_for_url("**/accounts/verify/done/")
    context.close()
    page.goto(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.wait_for_load_state("networkidle")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    alice_context = browser.new_context(viewport={"width": 360, "height": 900})
    bob_context = browser.new_context(viewport={"width": 360, "height": 900})
    alice, bob = alice_context.new_page(), bob_context.new_page()
    register(browser, alice, "Alice")
    alice.goto(args.url + "/communities/")
    community_name = "Voisins " + secrets.token_hex(3)
    alice.get_by_label("Nom de la communauté").fill(community_name)
    alice.get_by_role("button", name="Créer ma communauté", exact=True).click()
    community_url = alice.url
    alice.get_by_role("button", name="Créer un lien d'invitation", exact=True).click()
    invitation = alice.locator("textarea[readonly]").first.input_value()
    bob.goto(invitation)
    register(browser, bob, "Bob")
    bob.wait_for_url("**/communities/join/")
    bob.get_by_role("button", name="Confirmer mon adhésion", exact=True).click()
    check(bob.url == community_url, "Adhésion dans une communauté incorrecte")
    check("Alice" in bob.locator("main").inner_text(), "Membres absents")
    alice.reload()
    check("Bob" in alice.locator("main").inner_text(), "Adhésion non visible par l'administrateur")
    for width in (360, 768, 1280):
        alice.set_viewport_size({"width": width, "height": 900})
        check(
            not alice.evaluate("document.documentElement.scrollWidth > innerWidth"),
            "Débordement communauté",
        )
        alice.screenshot(path=f"work/community-{width}.png", full_page=True)
    print(
        "PASS communautés : création, invitation, inscription depuis lien, "
        "vérification séparée, adhésion explicite, responsive"
    )
    title = "Jeu scénario " + secrets.token_hex(4)
    alice.goto(args.url + "/games/new/")
    alice.get_by_label("Titre du jeu").fill(title)
    alice.get_by_label("Joueurs minimum").fill("2")
    alice.get_by_label("Joueurs maximum").fill("4")
    alice.get_by_role("button", name="Enregistrer", exact=True).click()
    game_url = alice.url
    alice.get_by_role("link", name="Ajouter mon exemplaire", exact=True).click()
    alice.get_by_label(community_name, exact=True).check()
    alice.get_by_label("État et commentaires de mon exemplaire").fill("Boîte Alice")
    alice.get_by_role("button", name="Enregistrer", exact=True).click()
    copy_url = alice.url
    bob.goto(game_url)
    bob.get_by_role("link", name="Ajouter mon exemplaire", exact=True).click()
    bob.get_by_label("État et commentaires de mon exemplaire").fill("Copie Bob privée")
    bob.get_by_role("button", name="Enregistrer", exact=True).click()
    bob_private_url = bob.url
    response = alice.goto(bob_private_url)
    check(response is not None and response.status == 404, "Fuite d'exemplaire privé")
    alice.goto(copy_url)
    bob.goto(copy_url)
    check("Boîte Alice" in bob.locator("main").inner_text(), "Exemplaire partagé invisible")
    outsider_context = browser.new_context(viewport={"width": 360, "height": 900})
    outsider = outsider_context.new_page()
    register(browser, outsider, "Clara")
    response = outsider.goto(copy_url)
    check(response is not None and response.status == 404, "Accès croisé à un exemplaire")
    for width in (360, 768, 1280):
        bob.set_viewport_size({"width": width, "height": 900})
        check(
            not bob.evaluate("document.documentElement.scrollWidth > innerWidth"),
            "Débordement exemplaire",
        )
        bob.screenshot(path=f"work/copy-{width}.png", full_page=True)
    print(
        "PASS catalogue/exemplaires : fiche réutilisée, partage choisi, "
        "copie privée, accès croisés refusés"
    )
    browser.close()
