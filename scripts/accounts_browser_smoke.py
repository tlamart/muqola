"""Parcours réel du lot 1 : navigateur, PostgreSQL et SMTP capturé dans Mailpit."""

import argparse
import json
import re
import secrets
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--mailpit", default="http://127.0.0.1:8025")
args = parser.parse_args()
Path("work").mkdir(exist_ok=True)


def mail_link(email: str, action: str) -> str:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with urlopen(args.mailpit + "/api/v1/messages", timeout=5) as response:  # noqa: S310
            messages = json.load(response)["messages"]
        for item in messages:
            if any(recipient["Address"] == email for recipient in item["To"]):
                with urlopen(args.mailpit + "/api/v1/message/" + item["ID"], timeout=5) as response:  # noqa: S310
                    body = json.load(response)["Text"]
                match = re.search(r"http[^\s]+/accounts/" + action + r"/[A-Za-z0-9_-]{43}/", body)
                if match:
                    return match.group(0)
        time.sleep(1)
    raise RuntimeError("E-mail attendu absent de Mailpit")


def password_fields(page: Page, value: str) -> None:
    page.locator('input[name="password"]').fill(value)
    page.locator('input[name="password_confirm"]').fill(value)


def login_form(page: Page, email: str, password: str) -> None:
    page.goto(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator('input[name="password"]').fill(password)
    page.get_by_role("button", name="Se connecter", exact=True).click()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    for width in (360, 1280):
        context = browser.new_context(viewport={"width": width, "height": 900})
        page = context.new_page()
        email = "browser-" + uuid.uuid4().hex[:12] + "@example.test"
        password = secrets.token_urlsafe(24)
        new_password = secrets.token_urlsafe(24)
        page.goto(args.url + "/accounts/signup/")
        page.get_by_label("Nom d'affichage").fill("Camille")
        page.get_by_label("Adresse e-mail").fill(email)
        password_fields(page, password)
        if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
            raise RuntimeError("Formulaire débordant")
        page.screenshot(path=f"work/signup-{width}.png", full_page=True)
        page.get_by_role("button", name="S'inscrire", exact=True).click()
        page.wait_for_url("**/accounts/signup/done/")
        login_form(page, email, password)
        page.wait_for_url("**/accounts/pending/")
        response = page.goto(args.url + "/accounts/dashboard/")
        if response is None or response.status != 403:
            raise RuntimeError("Un compte non vérifié accède au tableau de bord")
        verification_context = browser.new_context(viewport={"width": width, "height": 900})
        confirmation = verification_context.new_page()
        confirmation.goto(mail_link(email, "verify"))
        confirmation.get_by_role("button", name="Confirmer mon e-mail", exact=True).click()
        confirmation.wait_for_url("**/accounts/verify/done/")
        login_form(page, email, password)
        page.wait_for_url("**/accounts/dashboard/")
        if not page.get_by_role("heading", name="Bonjour Camille").is_visible():
            raise RuntimeError("Espace vérifié absent")
        page.screenshot(path=f"work/account-{width}.png", full_page=True)
        page.goto(args.url + "/accounts/reset/")
        page.get_by_label("Adresse e-mail").fill(email)
        page.get_by_role("button", name="Envoyer le lien").click()
        page.wait_for_url("**/accounts/email-sent/")
        confirmation.goto(mail_link(email, "reset"))
        password_fields(confirmation, new_password)
        confirmation.get_by_role("button", name="Enregistrer mon mot de passe").click()
        confirmation.wait_for_url("**/accounts/reset/done/")
        page.goto(args.url + "/accounts/dashboard/")
        page.wait_for_url("**/accounts/login/")
        login_form(page, email, new_password)
        page.wait_for_url("**/accounts/dashboard/")
        if page.get_by_role("button", name="Ouvrir le menu").is_visible():
            page.get_by_role("button", name="Ouvrir le menu").click()
        page.locator(".account-menu > summary").click()
        page.get_by_role("button", name="Se déconnecter").click()
        page.wait_for_url(args.url + "/")
        verification_context.close()
        context.close()
        print(
            f"PASS {width}px : inscription, SMTP capturé, vérification sans session, "
            "accès filtré, connexion, reset, session invalidée, déconnexion"
        )
    browser.close()
