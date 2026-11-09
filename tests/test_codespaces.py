import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import Client, override_settings

from config.codespaces_environment import origins
from scripts.codespaces import main, require_private_ports

ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT = {
    "CODESPACES": "true",
    "CODESPACE_NAME": "muqola-preview-ab123",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
    "APP_ENV": "development",
}
APPLICATION = "https://muqola-preview-ab123-8000.app.github.dev"


def test_codespaces_origins_are_exact_and_not_from_http_headers() -> None:
    assert origins(ENVIRONMENT) == (APPLICATION, "https://muqola-preview-ab123-8025.app.github.dev")


@pytest.mark.parametrize(
    "change",
    [
        {"CODESPACES": "false"},
        {"CODESPACES": ""},
        {"APP_ENV": "production"},
        {"APP_ENV": "test"},
        {"CODESPACE_NAME": ""},
        {"CODESPACE_NAME": "../../evil"},
        {"CODESPACE_NAME": "a.example.org"},
        {"CODESPACE_NAME": "space\nname"},
        {"GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "example.org"},
        {"GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev/evil"},
    ],
)
def test_codespaces_profile_refuses_unsafe_environment(change: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        origins(ENVIRONMENT | change)


def test_isolated_profile_sets_https_cookies_and_exact_trusted_origin() -> None:
    env = os.environ | ENVIRONMENT
    code = """
import json
import config.codespaces as s
print(json.dumps({
    'base': s.APP_BASE_URL, 'hosts': s.ALLOWED_HOSTS,
    'csrf': s.CSRF_TRUSTED_ORIGINS, 'session_secure': s.SESSION_COOKIE_SECURE,
    'csrf_secure': s.CSRF_COOKIE_SECURE, 'debug': s.DEBUG,
    'proxy': s.SECURE_PROXY_SSL_HEADER, 'mail': s.EMAIL_HOST,
}))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], env=env, cwd=ROOT, capture_output=True, text=True, check=True
    )
    settings = json.loads(result.stdout)
    assert settings["base"] == APPLICATION
    assert settings["csrf"] == [APPLICATION]
    assert settings["hosts"] == [
        "muqola-preview-ab123-8000.app.github.dev",
        "localhost",
        "127.0.0.1",
        "[::1]",
    ]
    assert settings["session_secure"] and settings["csrf_secure"]
    assert not settings["debug"] and settings["proxy"] is None
    assert settings["mail"] == "mailpit"


def test_production_does_not_inherit_codespaces_origins_or_cookie_exceptions() -> None:
    env = (
        os.environ
        | ENVIRONMENT
        | {"APP_ENV": "production", "APP_BASE_URL": "https://muqola.example.test"}
    )
    code = """
import json
import config.settings as s
csrf = getattr(s, 'CSRF_TRUSTED_ORIGINS', [])
print(json.dumps([s.APP_BASE_URL, csrf,
                  s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT]))
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], env=env, cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == ["https://muqola.example.test", [], True, True, True]
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.codespaces"],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "production" in result.stderr


@pytest.mark.parametrize(
    "ports",
    [
        [],
        [{"sourcePort": 8000, "visibility": "private"}],
        [
            {"sourcePort": 8000, "visibility": "public"},
            {"sourcePort": 8025, "visibility": "private"},
        ],
        [{"sourcePort": 8000, "visibility": "private"}, {"sourcePort": 8025, "visibility": "org"}],
        [
            {"sourcePort": 8000, "visibility": "private"},
            {"sourcePort": 8025, "visibility": "private"},
            {"sourcePort": 5432, "visibility": "private"},
        ],
    ],
)
def test_private_ports_gate_refuses_missing_public_or_extra_ports(
    ports: list[dict[str, object]],
) -> None:
    with pytest.raises(RuntimeError):
        require_private_ports(ports)


def test_private_ports_gate_accepts_only_the_two_private_http_ports() -> None:
    require_private_ports(
        [
            {"sourcePort": 8000, "visibility": "private"},
            {"sourcePort": 8025, "visibility": "private"},
        ]
    )


def test_start_never_builds_or_runs_services_when_visibility_cannot_be_verified() -> None:
    with (
        patch.dict(os.environ, ENVIRONMENT),
        patch("scripts.codespaces.subprocess.run") as run,
        patch("scripts.codespaces.github", side_effect=RuntimeError("private check failed")),
    ):
        with pytest.raises(RuntimeError, match="private check failed"):
            main()
    commands = [call.args[0] for call in run.call_args_list]
    assert any("stop" in command for command in commands)
    assert not any("build" in command or "up" in command for command in commands)


@pytest.mark.django_db
@override_settings(
    ALLOWED_HOSTS=["muqola-preview-ab123-8000.app.github.dev"],
    CSRF_TRUSTED_ORIGINS=[APPLICATION],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
)
def test_https_forwarded_origin_works_without_trusting_forwarded_proto() -> None:
    browser = Client(enforce_csrf_checks=True, HTTP_HOST="muqola-preview-ab123-8000.app.github.dev")
    browser.get("/accounts/signup/")
    token = browser.cookies["csrftoken"].value
    good = browser.post(
        "/accounts/signup/", {"csrfmiddlewaretoken": token}, HTTP_ORIGIN=APPLICATION
    )
    assert good.status_code == 200  # Formulaire incomplet, CSRF réellement accepté.
    bad = browser.post(
        "/accounts/signup/", {"csrfmiddlewaretoken": token}, HTTP_ORIGIN="https://evil.example.test"
    )
    assert bad.status_code == 403
    assert browser.get("/", HTTP_HOST="other-8000.app.github.dev").status_code == 400
