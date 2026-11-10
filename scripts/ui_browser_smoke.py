"""Parcours visuel réel, navigation mobile, filtres, sans JS et contenus longs.

Uniquement sur la pile de développement avec Mailpit : crée deux comptes fictifs
et leurs données via les formulaires réels. N'insère aucune donnée dans les vues.
"""

import argparse
import json
import re
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from playwright.sync_api import Browser, Page, expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
args = parser.parse_args()
output = Path("work/ui-redesign/screenshots")
output.mkdir(parents=True, exist_ok=True)
widths = (360, 390, 768, 1200, 1280)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def login(page: Page, email: str, password: str) -> None:
    page.goto(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.wait_for_url(re.compile(r"/(?:accounts/dashboard|communities/join)/$"))


def register(browser: Browser, page: Page, name: str) -> tuple[str, str]:
    email = "ui-" + secrets.token_hex(8) + "@example.test"
    password = secrets.token_urlsafe(24)
    page.goto(args.url + "/accounts/signup/")
    page.get_by_label("Nom d'affichage").fill(name)
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.locator("input[name=password_confirm]").fill(password)
    page.get_by_role("button", name="S'inscrire", exact=True).click()
    page.wait_for_url("**/accounts/signup/done/")
    link = ""
    for _ in range(30):
        with urlopen(args.mailpit + "/api/v1/messages", timeout=5) as response:  # noqa: S310
            messages = json.load(response)["messages"]
        for item in messages:
            if any(to["Address"] == email for to in item["To"]):
                with urlopen(args.mailpit + "/api/v1/message/" + item["ID"], timeout=5) as response:  # noqa: S310
                    body = json.load(response)["Text"]
                match = re.search(r"http[^\s]+/accounts/verify/[A-Za-z0-9_-]{43}/", body)
                if match:
                    link = match.group(0)
        if link:
            break
        time.sleep(1)
    check(bool(link), "Vérification absente de Mailpit")
    confirmation_context = browser.new_context()
    confirmation = confirmation_context.new_page()
    confirmation.goto(link)
    confirmation.get_by_role("button", name="Confirmer mon e-mail", exact=True).click()
    confirmation.wait_for_url("**/accounts/verify/done/")
    confirmation_context.close()
    login(page, email, password)
    return email, password


def geometry(page: Page) -> None:
    check(
        not page.evaluate("document.documentElement.scrollWidth > innerWidth"),
        "Débordement horizontal sur " + page.url.split("?")[0],
    )


def navigation(page: Page, width: int) -> None:
    menu = page.locator(".menu-toggle")
    nav = page.get_by_role("navigation", name="Navigation principale")
    if width < 1024:
        expect(menu).to_be_visible()
        expect(nav).to_be_hidden()
        menu.focus()
        page.keyboard.press("Enter")
        expect(menu).to_have_attribute("aria-expanded", "true")
        expect(nav).to_be_visible()
        page.keyboard.press("Tab")
        check(
            page.locator(":focus").get_attribute("href") == "/accounts/dashboard/",
            "Ordre clavier du menu incorrect",
        )
        page.keyboard.press("Escape")
        expect(nav).to_be_hidden()
        expect(menu).to_be_focused()
        expect(menu).to_have_attribute("aria-expanded", "false")
        menu.tap()
    else:
        expect(menu).to_be_hidden()
        expect(nav).to_be_visible()
    check(nav.locator(":scope > a").count() == 5, "Navigation métier incomplète")
    for label in ("Accueil", "Explorer les jeux", "Mes jeux", "Mes prêts", "Communautés"):
        expect(nav.get_by_role("link", name=label, exact=True)).to_be_visible()
    nav.locator(".account-menu > summary").click()
    expect(nav.get_by_role("link", name="Mon compte", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    check(
        not nav.locator(".account-menu").evaluate("element => element.open"),
        "Options du compte non refermées au clavier",
    )
    if width < 1024:
        page.keyboard.press("Escape")
        expect(nav).to_be_hidden()
    geometry(page)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    alice_context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    bob_context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    alice, bob = alice_context.new_page(), bob_context.new_page()
    failures: list[str] = []
    for page in (alice, bob):
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.on("requestfailed", lambda request: failures.append(request.url))
    register(browser, alice, "Alice")
    alice.goto(args.url + "/communities/")
    community_name = "Amis · Démo " + secrets.token_hex(2)
    alice.get_by_label("Nom de la communauté").fill(community_name)
    alice.get_by_role("button", name="Créer ma communauté", exact=True).click()
    community_url = alice.url
    alice.get_by_role("button", name="Créer un lien d'invitation", exact=True).click()
    invitation = alice.locator("textarea[readonly]").first.input_value()
    bob.goto(invitation)
    bob_email, bob_password = register(browser, bob, "Bob")
    bob.goto(invitation)
    bob.get_by_role("button", name="Confirmer mon adhésion", exact=True).click()
    game_urls: dict[str, str] = {}
    copy_urls: dict[str, str] = {}
    for title in ("Odin", "Régicide", "7 Wonders", "Cascadia"):
        alice.goto(args.url + "/games/new/")
        alice.get_by_label("Titre du jeu").fill(title)
        alice.get_by_label("Joueurs minimum").fill("1" if title == "Régicide" else "2")
        alice.get_by_label("Joueurs maximum").fill("4" if title == "Régicide" else "6")
        alice.get_by_label("Durée (minutes)").fill("30" if title == "Régicide" else "15")
        alice.get_by_role("button", name="Enregistrer", exact=True).click()
        game_urls[title] = alice.url
        alice.get_by_role("link", name="Ajouter mon exemplaire", exact=True).click()
        alice.get_by_label(community_name, exact=True).check()
        alice.get_by_role("button", name="Enregistrer", exact=True).click()
        copy_urls[title] = alice.url
    bob.goto(copy_urls["Odin"])
    bob.get_by_role("link", name="Demander ce jeu", exact=True).click()
    due_date = (datetime.now(ZoneInfo("Europe/Paris")).date() + timedelta(days=7)).isoformat()
    bob.locator("input[name=due_date]").fill(due_date)
    bob.get_by_role("button", name="Envoyer ma demande", exact=True).click()
    bob.wait_for_url("**/loans/*/")
    routes = {
        "accueil": args.url + "/",
        "explorer": args.url + "/copies/",
        "jeu": game_urls["Régicide"],
    }
    # L'accueil d'Alice montre sa demande reçue ; les deux autres écrans sont ceux de Bob.
    for width in widths:
        for name, url in routes.items():
            page = alice if name == "accueil" else bob
            page.set_viewport_size({"width": width, "height": 844 if width < 700 else 900})
            response = page.goto(url)
            check(response is not None and response.status == 200, "Écran principal indisponible")
            page.evaluate("document.fonts.ready")
            check(page.evaluate("document.fonts.check('700 22px Inter')"), "Police locale absente")
            geometry(page)
            check(
                "mailto:" not in page.locator("main").inner_html(), "Contact privé dans une fiche"
            )
            page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True)
            navigation(page, width)
        print(
            f"PASS UI {width}px : trois écrans, navigation clavier/tactile, menu et compte",
            flush=True,
        )
    # Resize avec le menu ouvert : aucune navigation cachée par un ancien état mobile.
    bob.set_viewport_size({"width": 390, "height": 844})
    bob.locator(".menu-toggle").click()
    bob.set_viewport_size({"width": 1280, "height": 900})
    expect(bob.locator("#site-navigation")).to_be_visible()
    expect(bob.locator(".menu-toggle")).to_be_hidden()
    bob.goto(routes["explorer"])
    bob.get_by_label("Rechercher un jeu par titre").fill("regicide")
    bob.get_by_role("button", name="Rechercher", exact=True).click()
    expect(bob.locator(".game-card")).to_have_count(1)
    expect(bob.locator(".game-card h3")).to_have_text("Régicide")
    bob.locator(".filter-disclosure > summary").click()
    bob.get_by_label("Communauté", exact=True).select_option(label=community_name)
    bob.get_by_label("Nombre de joueurs", exact=True).fill("2")
    bob.get_by_label("Disponibles uniquement", exact=True).check()
    bob.get_by_role("button", name="Rechercher", exact=True).click()
    expect(bob.locator(".game-card")).to_have_count(1)
    bob.get_by_label("Rechercher un jeu par titre").fill("Aucun jeu de ce nom")
    bob.get_by_role("button", name="Rechercher", exact=True).click()
    expect(bob.get_by_role("heading", name="Aucun jeu ne correspond")).to_be_visible()
    bob.goto(game_urls["Régicide"])
    bob.get_by_role("link", name="Demander ce jeu", exact=True).click()
    date_field = bob.locator("input[name=due_date]")
    check(date_field.get_attribute("required") is not None, "Date de retour non obligatoire")
    date_field.fill(due_date)
    bob.get_by_role("button", name="Envoyer ma demande", exact=True).click()
    bob.wait_for_url("**/loans/*/")
    print("PASS UI : filtres réels, recherche sans accents, état vide et demande datée", flush=True)
    # Sans JS : navigation complète et soumission native sur le vrai serveur.
    nojs_context = browser.new_context(
        java_script_enabled=False, viewport={"width": 360, "height": 844}
    )
    nojs = nojs_context.new_page()
    login(nojs, bob_email, bob_password)
    expect(nojs.locator("#site-navigation")).to_be_visible()
    expect(nojs.locator(".menu-toggle")).to_be_hidden()
    geometry(nojs)
    nojs.goto(routes["explorer"])
    nojs.get_by_label("Rechercher un jeu par titre").fill("Cascadia")
    nojs.get_by_role("button", name="Rechercher", exact=True).click()
    expect(nojs.locator(".game-card")).to_have_count(1)
    geometry(nojs)
    nojs_context.close()
    # Données longues saisies par les formulaires, après les captures de référence.
    alice.goto(game_urls["Régicide"] + "edit/")
    long_title = "Partage" * 17
    alice.get_by_label("Titre du jeu").fill(long_title)
    alice.get_by_label("Description générique").fill("Une partie à partager. " * 80)
    alice.get_by_role("button", name="Enregistrer", exact=True).click()
    alice.goto(copy_urls["Régicide"] + "edit/")
    alice.get_by_label("État et commentaires de mon exemplaire").fill("Commentaire" * 45)
    alice.get_by_role("button", name="Enregistrer", exact=True).click()
    alice.goto(community_url)
    alice.get_by_label("Nom de la communauté").fill("Communauté" * 10)
    alice.get_by_role("button", name="Enregistrer les paramètres", exact=True).click()
    for width in widths:
        for url in (routes["explorer"], game_urls["Régicide"], community_url):
            alice.set_viewport_size({"width": width, "height": 900})
            alice.goto(url)
            geometry(alice)
    check(not failures, "Erreurs JavaScript ou ressources réseau : " + str(failures))
    print(
        "PASS UI : sans JavaScript, contenus longs aux cinq largeurs, aucune erreur JS/réseau",
        flush=True,
    )
    (output.parent / "result.json").write_text(
        json.dumps(
            {
                "widths": widths,
                "screens": list(routes),
                "screenshots": 15,
                "navigation": "passed",
                "filters": "passed",
                "without_js": "passed",
                "long_content": "passed",
                "network_errors": failures,
            },
            indent=2,
        )
        + "\n"
    )
    browser.close()
