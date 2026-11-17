"""Proxy assertions cover identity, protocol and both rate-limit dimensions."""

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from muqola.core.proxy import TrustedProxyMiddleware, canonical_ip, client_ip
from muqola.identity.ratelimit import allowed


@override_settings(APP_ENV="production", TRUSTED_PROXY_IPS=["192.0.2.10"])
def test_only_configured_peer_can_supply_a_single_client_ip() -> None:
    factory = RequestFactory()
    request = factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.1")
    assert client_ip(request) == "198.51.100.1"
    for header in ("198.51.100.1, 198.51.100.2", "not-an-ip", "", "fe80::1%eth0"):
        request.META["HTTP_X_REAL_IP"] = header
        assert client_ip(request) == "192.0.2.10"
    request.META.update(REMOTE_ADDR="192.0.2.11", HTTP_X_REAL_IP="198.51.100.1")
    assert client_ip(request) == "192.0.2.11"
    assert canonical_ip("::ffff:192.0.2.10") == "192.0.2.10"


@override_settings(
    APP_ENV="production",
    TRUSTED_PROXY_IPS=["192.0.2.10"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
@pytest.mark.parametrize("peer,trusted", [("192.0.2.10", True), ("192.0.2.11", False)])
def test_untrusted_forwarding_cannot_claim_https(peer: str, trusted: bool) -> None:
    request = RequestFactory().get(
        "/accounts/signup/",
        REMOTE_ADDR=peer,
        HTTP_X_FORWARDED_PROTO="https",
        HTTP_X_REAL_IP="198.51.100.1",
        HTTP_X_FORWARDED_HOST="forged.example.test",
    )

    def next_handler(incoming: HttpRequest) -> HttpResponse:
        assert incoming.is_secure() is trusted
        return HttpResponse()

    TrustedProxyMiddleware(next_handler)(request)
    if not trusted:
        assert "HTTP_X_REAL_IP" not in request.META
        assert "HTTP_X_FORWARDED_HOST" not in request.META


@override_settings(APP_ENV="production", TRUSTED_PROXY_IPS=[])
def test_loopback_probe_exception_is_limited_to_health_routes() -> None:
    for path, retained in (("/health/ready/", True), ("/accounts/signup/", False)):
        request = RequestFactory().get(
            path, REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_PROTO="https"
        )
        TrustedProxyMiddleware(lambda _: HttpResponse())(request)
        assert ("HTTP_X_FORWARDED_PROTO" in request.META) is retained


@override_settings(APP_ENV="development", TRUSTED_PROXY_IPS=["192.0.2.10"])
def test_local_configuration_never_trusts_forwarded_identity() -> None:
    request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.1")
    assert client_ip(request) == "192.0.2.10"


@pytest.mark.django_db
@override_settings(APP_ENV="production", TRUSTED_PROXY_IPS=["192.0.2.10"])
def test_clients_have_separate_ip_budgets_and_shared_email_budget() -> None:
    factory = RequestFactory()
    first = factory.post("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.1")
    second = factory.post("/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP="198.51.100.2")
    for _ in range(10):
        assert allowed(first, "signup")
    assert not allowed(first, "signup")
    assert allowed(second, "signup")
    for index in range(10):
        request = factory.post(
            "/", REMOTE_ADDR="192.0.2.10", HTTP_X_REAL_IP=f"203.0.113.{index + 1}"
        )
        assert allowed(request, "login", "same@example.test")
    assert not allowed(second, "login", "SAME@example.test")
