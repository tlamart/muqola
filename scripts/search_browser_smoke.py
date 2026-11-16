"""Real local PostgreSQL/HTML search with controlled clocks and response ordering.

Synthetic accounts/data only, no external service. Runs against Compose, never production.
"""

import argparse
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from catalogue_fixture import local_command
from playwright.sync_api import Route, expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--browser", default="/usr/bin/chromium")
parser.add_argument("--url", default="http://localhost:8000")
args = parser.parse_args()
if urlparse(args.url).hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("Pile locale synthétique uniquement.")
prefix = secrets.token_hex(6)
password = secrets.token_urlsafe(24)
email = f"search-{prefix}@example.test"
setup = """
from django.conf import settings
from django.utils import timezone
from muqola.identity.models import User
from muqola.catalogue.models import Game, GameAlias
from muqola.communities.models import Community, Membership
from muqola.inventory.models import OwnedGame, GameVisibility
assert settings.APP_ENV == "development"
reader = User(email={email}, display_name="Recherche fictive", email_verified_at=timezone.now())
reader.set_password({password}); reader.save()
owner = User.objects.create(email={owner_email}, display_name="Prêteur fictif",
    password="!", email_verified_at=timezone.now())
community = Community.objects.create(name={community}, created_by=owner)
for user in (owner, reader): Membership.objects.create(user=user, community=community)
for i in range(45):
    game = Game.objects.create(title=f"Quête {prefix} {{i:02}}",
        moderation_status="approved", kind="standalone", created_by=owner)
    GameAlias.objects.create(game=game, title=f"Couronne {prefix} {{i:02}}")
    for j in range(2):
        copy = OwnedGame.objects.create(game=game, owner=owner)
        GameVisibility.objects.create(owned_game=copy, community=community)
""".format(
    email=repr(email),
    password=repr(password),
    owner_email=repr(f"owner-{prefix}@example.test"),
    community=repr(f"Groupe {prefix}"),
    prefix=prefix,
)
local_command("shell", content=setup)
output = Path("work/search")
output.mkdir(parents=True, exist_ok=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=args.browser)
    context = browser.new_context(viewport={"width": 360, "height": 844})
    page = context.new_page()
    violations: list[str] = []
    page.add_init_script(
        "document.addEventListener('securitypolicyviolation', "
        "e => console.error('CSP:' + e.violatedDirective))"
    )
    page.on(
        "console",
        lambda message: (
            violations.append(message.text) if message.text.startswith("CSP:") else None
        ),
    )
    page.goto(args.url + "/accounts/login/")
    page.get_by_label("Adresse e-mail").fill(email)
    page.locator("input[name=password]").fill(password)
    page.get_by_role("button", name="Se connecter", exact=True).click()
    page.wait_for_url("**/accounts/dashboard/")
    state = context.storage_state()
    page.goto(args.url + "/games/?title=" + prefix)
    input = page.get_by_label("Rechercher un jeu par titre", exact=True)
    expect(page.locator("[data-result-count]")).to_have_attribute("data-result-count", "45")
    page.clock.install()
    page.clock.pause_at(datetime.now(UTC) + timedelta(seconds=1))
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url)
            if request.headers.get("x-requested-with") == "live-search"
            else None
        ),
    )
    input.fill("q")
    page.clock.run_for(500)
    check(len(requests) == 0, "No request for one character")
    expect(page.locator("#search-status")).to_contain_text("deux caractères")
    input.fill("qu")
    page.clock.run_for(249)
    check(len(requests) == 0, "No request before debounce")
    with page.expect_response(
        lambda response: response.request.headers.get("x-requested-with") == "live-search"
    ):
        page.clock.run_for(1)
    check(len(requests) == 1, "One request after debounce")
    expect(input).to_be_focused()
    expect(page.locator("#search-results")).to_have_attribute("aria-busy", "false")
    page.locator("input[type=radio][name=game_id]").first.check()
    selected = page.locator("#selected-game").input_value()
    page.get_by_label("État et commentaires de mon exemplaire").fill("Notes conservées")
    page.get_by_label(f"Groupe {prefix}", exact=True).check()
    input.fill("Introuvable-xyz")
    page.clock.run_for(250)
    expect(page.locator("[data-result-count]")).to_have_attribute("data-result-count", "0")
    expect(page.locator("#selected-game")).to_have_value(selected)
    expect(page.locator("#selection-status")).to_contain_text("Choix conservé")
    expect(page.get_by_label("État et commentaires de mon exemplaire")).to_have_value(
        "Notes conservées"
    )
    expect(page.get_by_label(f"Groupe {prefix}", exact=True)).to_be_checked()
    # IME never searches an unfinished composition, and submits once afterwards.
    before = len(requests)
    input.dispatch_event("compositionstart")
    input.fill("Couronne " + prefix)
    page.clock.run_for(1000)
    check(len(requests) == before, "No fetch during composition")
    input.dispatch_event("compositionend")
    page.clock.run_for(250)
    expect(page.locator(".catalogue-choices strong").first).to_contain_text(prefix)
    check(len(requests) == before + 1, "One fetch after composition")
    # Force a transport that cannot cancel, to test the generation guard itself.
    page.evaluate("""() => {
      window.originalSearchFetch = window.fetch;
      window.searchAborts = 0;
      window.fetch = (url, options) => {
        options.signal.addEventListener('abort', () => window.searchAborts++);
        return window.originalSearchFetch(url, {...options, signal: undefined});
      };
    }""")
    held: list[Route] = []

    def hold(route: Route) -> None:
        held.append(route)

    page.route("**/games/?**", hold)
    input.fill("Ancien-xyz")
    page.clock.run_for(250)
    expect(page.locator("#search-results")).to_have_attribute("aria-busy", "true")
    # Give the dispatched route a turn without advancing the application clock.
    page.wait_for_function("true")
    check(len(held) == 1, "Old response is held")
    old = held[0]
    old_response = old.fetch()
    input.fill(prefix)
    page.clock.run_for(250)
    page.wait_for_function("true")
    check(len(held) == 2, "New response is held")
    held[1].fulfill(response=held[1].fetch())
    expect(page.locator("[data-result-count]")).to_have_attribute("data-result-count", "45")
    old.fulfill(response=old_response)
    expect(page.locator("#search-status")).to_have_text("45 résultats.")
    check(page.evaluate("window.searchAborts") >= 1, "Previous transport received abort")
    page.unroute("**/games/?**", hold)
    page.evaluate("window.fetch = window.originalSearchFetch")
    input.fill("")
    page.clock.run_for(250)
    expect(page.locator("#search-results")).to_have_attribute("aria-busy", "false")
    # A failed fetch preserves the choice and gives a working native GET retry.
    page.route("**/games/?**", lambda route: route.abort())
    input.fill("Quete " + prefix)
    page.clock.run_for(250)
    expect(page.locator("#search-status")).to_contain_text("indisponible")
    expect(page.locator("#selected-game")).to_have_value(selected)
    page.unroute("**/games/?**")
    input.press("Enter")
    page.wait_for_url("**/games/?title=Quete*")
    expect(page.locator("input[type=radio][name=game_id]")).to_have_count(10)
    # Actual selection can still be posted after fragment replacements.
    page.locator("input[type=radio][name=game_id]").first.check()
    page.get_by_role("button", name="Ajouter à ma collection", exact=True).click()
    page.wait_for_url("**/copies/*/")
    page.goto(args.url + "/copies/?title=" + prefix)
    expect(page.locator(".game-card")).to_have_count(30)
    expect(page.locator("[data-result-count]")).to_have_attribute("data-result-count", "45")
    expect(page.locator(".game-card").first).to_contain_text("2 exemplaires accessibles")
    page.locator(".pagination").get_by_role("link", name="Page suivante").click()
    expect(page.locator(".game-card")).to_have_count(15)
    expect(page.locator(".pagination")).to_contain_text("Page 2 sur 2")
    page.locator(".filter-disclosure summary").click()
    page.get_by_label("Nombre de joueurs", exact=True).fill("2")
    page.get_by_label("Disponibles uniquement", exact=True).check()
    page.clock.run_for(250)
    expect(page.locator(".game-card")).to_have_count(30)
    expect(page.locator(".pagination")).to_contain_text("Page 1 sur 2")
    check(
        not page.evaluate("document.documentElement.scrollWidth > innerWidth"),
        "No horizontal overflow at 360px",
    )
    page.screenshot(path=str(output / "search-360.png"), full_page=True)
    check(not violations, "No horizontal overflow at 360px")
    context.close()
    for width in (360, 1280):
        nojs = browser.new_context(
            storage_state=state, java_script_enabled=False, viewport={"width": width, "height": 900}
        )
        page = nojs.new_page()
        page.goto(args.url + "/copies/")
        page.get_by_label("Rechercher un jeu par titre").fill("Couronne " + prefix)
        page.get_by_label("Rechercher un jeu par titre").press("Enter")
        expect(page.locator("[data-result-count]")).to_have_attribute("data-result-count", "45")
        expect(page.locator(".game-card")).to_have_count(30)
        page.locator(".game-card__link").first.click()
        expect(page.get_by_role("link", name="Demander ce jeu", exact=True)).to_have_count(2)
        check(
            not page.evaluate("document.documentElement.scrollWidth > innerWidth"),
            "No horizontal overflow without JavaScript",
        )
        nojs.close()
    browser.close()
print(
    json.dumps(
        {
            "result": "PASS",
            "checks": [
                "250ms/min2",
                "IME",
                "abort/stale",
                "selection/notes/shares",
                "network/native retry",
                "grouping/pagination/filters",
                "CSP",
                "360px",
                "noJS Enter",
            ],
        }
    )
)
