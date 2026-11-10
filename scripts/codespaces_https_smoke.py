"""Teste le backend HTTP derrière l'origine HTTPS déclarée ; ne simule pas le login GitHub."""

import http.client
import json
import os
import re
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from config.codespaces_environment import origins

origin, _ = origins(os.environ)
host = str(urlsplit(origin).hostname)
backend_port = int(os.environ.get("CODESPACES_SMOKE_PORT", "8000"))
cookies: dict[str, str] = {}


def request(
    method: str, path: str, data: dict[str, str] | None = None, request_origin: str = origin
) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=10)
    headers = {"Host": host, "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
    if method == "POST":
        headers.update(
            {"Origin": request_origin, "Content-Type": "application/x-www-form-urlencoded"}
        )
    connection.request(
        method, path, body=urlencode(data or {}) if method == "POST" else None, headers=headers
    )
    response = connection.getresponse()
    response_headers = dict(response.getheaders())
    for key, value in response.getheaders():
        if key.lower() == "set-cookie":
            parsed: SimpleCookie[str] = SimpleCookie()
            parsed.load(value)
            for name, morsel in parsed.items():
                if not morsel["secure"]:
                    raise RuntimeError("Un cookie du profil HTTPS n'est pas Secure")
                if morsel["domain"]:
                    raise RuntimeError("Un cookie déborde du seul hôte applicatif")
                if name == "sessionid" and (not morsel["httponly"] or morsel["samesite"] != "Lax"):
                    raise RuntimeError("Attributs de session incorrects")
                cookies[name] = morsel.value
    text = response.read().decode()
    status = response.status
    connection.close()
    return status, response_headers, text


def csrf(page: str) -> str:
    match = re.search(r'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"', page)
    if not match:
        raise RuntimeError("Jeton CSRF absent")
    return match.group(1)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


_, _, page = request("GET", "/accounts/signup/")
email = "https-profile-" + secrets.token_hex(6) + "@example.test"
password = secrets.token_urlsafe(24)
status, _, _ = request(
    "POST",
    "/accounts/signup/",
    {
        "csrfmiddlewaretoken": csrf(page),
        "display_name": "Camille",
        "email": email,
        "password": password,
        "password_confirm": password,
    },
)
expect(status == 302, "Inscription refusée derrière l'origine HTTPS")
link = ""
for _ in range(30):
    with urlopen("http://127.0.0.1:8025/api/v1/messages", timeout=5) as response:  # noqa: S310
        messages = json.load(response)["messages"]
    for item in messages:
        if any(recipient["Address"] == email for recipient in item["To"]):
            with urlopen(
                "http://127.0.0.1:8025/api/v1/message/" + item["ID"], timeout=5
            ) as response:  # noqa: S310
                body = json.load(response)["Text"]
            match = re.search(re.escape(origin) + r"/accounts/verify/[A-Za-z0-9_-]{43}/", body)
            if match:
                link = match.group(0)
    if link:
        break
    time.sleep(1)
expect(bool(link), "Lien HTTPS de vérification absent de Mailpit")
status, headers, _ = request("GET", urlsplit(link).path)
expect(status == 302, "Ouverture du lien refusée")
_, _, page = request("GET", headers["Location"])
status, _, _ = request("POST", "/accounts/verify/confirm/", {"csrfmiddlewaretoken": csrf(page)})
expect(status == 302, "Confirmation refusée")
_, _, page = request("GET", "/accounts/login/")
status, _, _ = request(
    "POST",
    "/accounts/login/",
    {
        "csrfmiddlewaretoken": csrf(page),
        "email": email,
        "password": password,
    },
)
expect(status == 302 and "sessionid" in cookies, "Connexion HTTPS refusée")
status, _, _ = request("GET", "/accounts/dashboard/")
expect(status == 200, "Espace vérifié inaccessible")
status, _, _ = request(
    "POST",
    "/accounts/logout/",
    {
        "csrfmiddlewaretoken": cookies["csrftoken"],
    },
    request_origin="https://evil.example.test",
)
expect(status == 403, "Une origine étrangère a passé CSRF")
print(
    "PASS profil Codespaces : inscription, lien HTTPS capturé, vérification, "
    "connexion, cookies Secure, CSRF"
)
