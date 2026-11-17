"""Private HTTPS probe: verified TLS, access barrier and no credential redirects."""

import base64
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from deploy.common import OperationError, config_file


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


def load_credentials(path: Path) -> tuple[str, str]:
    credentials = config_file(path)
    username, password = credentials["username"], credentials["password"]
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not username
        or len(password) < 16
        or ":" in username
        or any(char in username + password for char in ("\n", "\r"))
    ):
        raise OperationError("invalid_probe_credentials")
    return username, password


def validate_origin(url: str) -> None:
    origin = urlsplit(url)
    if origin.scheme != "https" or origin.username or origin.password or origin.fragment:
        raise OperationError("https_probe_origin_required")


def private_access_blocked(url: str, *, ca_file: str | None = None) -> bool:
    validate_origin(url)
    context = ssl.create_default_context(cafile=ca_file)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    try:
        with opener.open(url, timeout=5):  # noqa: S310 -- HTTPS verified above
            return False
    except HTTPError as error:
        return error.code == 401 and "noindex" in error.headers.get("X-Robots-Tag", "")


def protected_probe(url: str, credentials_file: Path, *, ca_file: str | None = None) -> bool:
    validate_origin(url)
    username, password = load_credentials(credentials_file)
    if not private_access_blocked(url, ca_file=ca_file):
        raise OperationError("staging_access_not_private")
    token = base64.b64encode((username + ":" + password).encode()).decode()
    context = ssl.create_default_context(cafile=ca_file)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    request = Request(url, headers={"Authorization": "Basic " + token})  # noqa: S310 -- HTTPS validated
    with opener.open(request, timeout=5) as response:
        return bool(response.status == 200)
