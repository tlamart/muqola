"""Smoke navigateur du seul accueil lot 0, à 360 px et sur desktop."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://127.0.0.1:8000")
args = parser.parse_args()
Path("work").mkdir(exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    for width in (360, 1280):
        page = browser.new_page(viewport={"width": width, "height": 900})
        failures: list[str] = []
        page.on("pageerror", lambda error, errors=failures: errors.append(str(error)))
        page.on("requestfailed", lambda request, errors=failures: errors.append(request.url))
        response = page.goto(args.url, wait_until="networkidle")
        if response is None or response.status != 200:
            raise RuntimeError("Accueil inaccessible")
        if page.locator("html").get_attribute("lang") != "fr":
            raise RuntimeError("Langue française manquante")
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            raise RuntimeError(f"Débordement horizontal à {width}px")
        if page.locator("ol.steps > li").count() != 3:
            raise RuntimeError("Présentation incomplète")
        page.keyboard.press("Tab")
        if page.locator(":focus").inner_text() != "Aller au contenu":
            raise RuntimeError("Lien d'évitement clavier inaccessible")
        page.keyboard.press("Enter")
        if page.evaluate("getComputedStyle(document.body).backgroundColor") != "rgb(248, 247, 252)":
            raise RuntimeError("Feuille CSS non chargée")
        if failures:
            raise RuntimeError(str(failures))
        page.screenshot(path=f"work/home-{width}.png", full_page=True)
        print(f"PASS {width}px : HTTP 200, CSS, français, clavier, aucun débordement/échec réseau")
        page.close()
    browser.close()
