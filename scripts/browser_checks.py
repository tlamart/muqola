"""Distingue une recherche locale annulée d'une véritable erreur réseau."""

from urllib.parse import urlsplit

from playwright.sync_api import Page, Request, expect


def open_invitation(page: Page, *, settings: bool = False) -> None:
    if not page.locator("#invitation-heading").is_visible():
        page.get_by_text("Inviter des membres", exact=True).click()
    expect(page.locator("#invitation-heading")).to_be_visible()
    if settings:
        control = page.get_by_label("Paramètres du lien d’invitation", exact=True)
        if control.get_attribute("aria-expanded") != "true" and not control.evaluate(
            "e => e.parentElement.open"
        ):
            control.click()


def open_community_settings(page: Page) -> None:
    if not page.locator("#community-settings-heading").is_visible():
        page.get_by_text("Modifier les paramètres", exact=True).click()
    expect(page.locator("#community-settings-heading")).to_be_visible()


def continue_copy(page: Page) -> None:
    page.get_by_role("button", name="Continuer vers mon exemplaire", exact=True).click()
    expect(page.get_by_role("heading", name="Votre exemplaire", exact=True)).to_be_visible()


def expected_search_abort(request: Request, app_url: str) -> bool:
    target, origin = urlsplit(request.url), urlsplit(app_url)
    return (
        request.failure == "net::ERR_ABORTED"
        and request.resource_type == "fetch"
        and request.headers.get("x-requested-with") == "live-search"
        and (target.scheme, target.netloc) == (origin.scheme, origin.netloc)
        and target.path in {"/games/", "/copies/"}
    )
