"""Distingue une recherche locale annulée d'une véritable erreur réseau."""

from urllib.parse import urlsplit

from playwright.sync_api import Request


def expected_search_abort(request: Request, app_url: str) -> bool:
    target, origin = urlsplit(request.url), urlsplit(app_url)
    return (
        request.failure == "net::ERR_ABORTED"
        and request.resource_type == "fetch"
        and request.headers.get("x-requested-with") == "live-search"
        and (target.scheme, target.netloc) == (origin.scheme, origin.netloc)
        and target.path in {"/games/", "/copies/"}
    )
