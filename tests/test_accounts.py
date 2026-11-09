import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import SESSION_KEY
from django.core import mail
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from muqola.identity.models import AccountToken, RateBucket, User
from muqola.identity.ratelimit import allowed
from muqola.identity.services import (
    consume_token,
    purge_ephemeral_data,
    register,
    request_token,
    token_digest,
)
from muqola.notifications.models import EmailOutbox
from muqola.notifications.services import cipher, send_due

PASSWORD = "Rivages-fictifs-8264!"
NEW_PASSWORD = "Montagnes-fictives-5739!"
pytestmark = pytest.mark.django_db


def signup(client: Client, email: str = "alice@example.test") -> tuple[int, str]:
    response = client.post(
        reverse("identity:signup"),
        {
            "email": email,
            "display_name": "Alice",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
    )

    return response.status_code, response["Location"]


def raw_token(item: EmailOutbox | None = None) -> str:
    if item is None:
        item = EmailOutbox.objects.latest("created_at")
    payload = json.loads(cipher().decrypt(item.encrypted_payload.encode()))
    match = re.search(r"/accounts/(?:verify|reset)/([A-Za-z0-9_-]{43})/", payload["body"])
    assert match is not None
    return match.group(1)


def account(verified: bool = False) -> User:
    return User.objects.create_user(
        "alice@example.test",
        PASSWORD,
        display_name="Alice",
        email_verified_at=timezone.now() if verified else None,
    )


@override_settings(ALLOWED_HOSTS=["untrusted.example.org"])
def test_open_signup_normalizes_email_hashes_password_and_queues_encrypted_message(
    client: Client,
) -> None:
    response = client.post(
        reverse("identity:signup"),
        {
            "email": " Alice@Example.test ",
            "display_name": "Alice",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        HTTP_HOST="untrusted.example.org",
    )
    assert response.status_code == 302
    user = User.objects.get()
    assert user.email == "alice@example.test"
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD
    assert user.email_verified_at is None
    assert SESSION_KEY not in client.session
    token = AccountToken.objects.get()
    queued = EmailOutbox.objects.get()
    raw = raw_token(queued)
    assert token.digest == token_digest(raw)
    assert (
        timedelta(hours=23, minutes=59) < token.expires_at - token.created_at <= timedelta(hours=24)
    )
    assert raw not in queued.encrypted_payload
    assert user.email not in queued.encrypted_payload
    assert raw not in str(client.session.items())
    payload = cipher().decrypt(queued.encrypted_payload.encode()).decode()
    assert "http://localhost:8000/accounts/verify/" in payload
    assert "untrusted.example.org" not in payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "pas-un-email"},
        {"display_name": ""},
        {"display_name": "a" * 81},
        {"password": "123456789012", "password_confirm": "123456789012"},
        {"password": "court", "password_confirm": "court"},
        {"password_confirm": "autre"},
    ],
)
def test_signup_server_validation(client: Client, overrides: dict[str, str]) -> None:
    data = {
        "email": "alice@example.test",
        "display_name": "Alice",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    } | overrides
    response = client.post(reverse("identity:signup"), data)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert User.objects.count() == 0
    assert EmailOutbox.objects.count() == 0
    assert PASSWORD not in response.content.decode()


def test_duplicate_signup_has_same_public_response_and_does_not_overwrite(client: Client) -> None:
    first = signup(client)
    user = User.objects.get()
    original_hash = user.password
    second = client.post(
        reverse("identity:signup"),
        {
            "email": "ALICE@example.test",
            "display_name": "Autre",
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )
    assert first[0] == second.status_code == 302
    assert first[1] == second["Location"]
    user.refresh_from_db()
    assert user.display_name == "Alice" and user.password == original_hash
    assert User.objects.count() == EmailOutbox.objects.count() == 1


def test_case_normalization_is_enforced_even_on_direct_database_write() -> None:
    account()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(email="alice@example.test").update(email="ALICE@example.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("ALICE@example.test", PASSWORD)


def test_signup_and_email_are_atomic_on_queue_failure() -> None:
    with (
        patch("muqola.identity.services.enqueue_account_email", side_effect=RuntimeError),
        pytest.raises(RuntimeError),
    ):
        register("alice@example.test", "Alice", PASSWORD)
    assert not User.objects.exists()
    assert not AccountToken.objects.exists()


def test_verification_without_login_get_does_not_consume_and_post_is_single_use(
    client: Client,
) -> None:
    signup(client)
    raw = raw_token()
    fresh_browser = Client()
    response = fresh_browser.get(reverse("identity:verify", args=[raw]))
    assert response.status_code == 302
    assert raw not in response["Location"]
    assert response["Referrer-Policy"] == "no-referrer"
    assert AccountToken.objects.get().consumed_at is None
    assert fresh_browser.get(response["Location"]).status_code == 200
    result = fresh_browser.post(response["Location"])
    assert result.status_code == 302
    assert User.objects.get().email_verified_at is not None
    assert AccountToken.objects.get().consumed_at is not None
    assert SESSION_KEY not in fresh_browser.session
    fresh_browser.get(reverse("identity:verify", args=[raw]))
    assert fresh_browser.post(reverse("identity:verify-confirm")).status_code == 400


@pytest.mark.parametrize("purpose", [AccountToken.Purpose.VERIFY, AccountToken.Purpose.RESET])
def test_expired_wrong_purpose_and_disabled_account_tokens_are_rejected(purpose: str) -> None:
    user = account()
    request_token(user.email, purpose)
    raw = raw_token()
    digest = token_digest(raw)
    other = "reset" if purpose == "verify" else "verify"
    assert not consume_token(digest, other, NEW_PASSWORD)
    AccountToken.objects.update(
        expires_at=timezone.now() - timedelta(seconds=1),
        created_at=timezone.now() - timedelta(days=2),
    )
    assert not consume_token(digest, purpose, NEW_PASSWORD)
    request_token(user.email, purpose)
    digest = token_digest(raw_token())
    user.is_active = False
    user.save()
    assert not consume_token(digest, purpose, NEW_PASSWORD)


def test_resend_invalidates_old_link_without_requiring_session(client: Client) -> None:
    signup(client)
    old = raw_token()
    response = client.post(reverse("identity:resend"), {"email": "ALICE@example.test"})
    assert response.status_code == 302
    new = raw_token()
    assert new != old
    assert not consume_token(token_digest(old), "verify")
    assert consume_token(token_digest(new), "verify")


@pytest.mark.parametrize("route", ["resend", "reset-request"])
def test_email_requests_do_not_disclose_account_existence(client: Client, route: str) -> None:
    account()
    known = client.post(reverse("identity:" + route), {"email": "alice@example.test"}, follow=True)
    unknown = client.post(
        reverse("identity:" + route), {"email": "absent@example.test"}, follow=True
    )
    assert known.status_code == unknown.status_code == 200
    assert known.content == unknown.content


def test_login_unverified_is_limited_and_cannot_open_dashboard(client: Client) -> None:
    user = account()
    response = client.post(
        reverse("identity:login"), {"email": "ALICE@example.test", "password": PASSWORD}
    )
    assert response["Location"] == reverse("identity:pending")
    assert client.get(reverse("identity:pending")).status_code == 200
    assert client.get(reverse("identity:dashboard")).status_code == 403
    user.email_verified_at = timezone.now()
    user.save()
    assert client.get(reverse("identity:dashboard")).status_code == 200


def test_anonymous_redirect_and_session_fixation_logout(client: Client) -> None:
    account(verified=True)
    assert client.get(reverse("identity:dashboard"))["Location"] == reverse("identity:login")
    session = client.session
    session["before_login"] = True
    session.save()
    old_key = session.session_key
    login_response = client.post(
        reverse("identity:login") + "?next=https://evil.example.org",
        {
            "email": "alice@example.test",
            "password": PASSWORD,
        },
    )
    assert login_response["Location"] == reverse("identity:dashboard")
    assert client.session.session_key != old_key
    assert client.get(reverse("identity:logout")).status_code == 405
    assert client.post(reverse("identity:logout")).status_code == 302
    assert SESSION_KEY not in client.session


@pytest.mark.parametrize("existing,inactive", [(False, False), (True, False), (True, True)])
def test_login_failure_is_generic(client: Client, existing: bool, inactive: bool) -> None:
    if existing:
        user = account()
        user.is_active = not inactive
        user.save()
    response = client.post(
        reverse("identity:login"),
        {
            "email": "alice@example.test",
            "password": "incorrect",
        },
    )
    assert "Adresse ou mot de passe incorrect." in response.content.decode()
    assert SESSION_KEY not in client.session


def test_password_reset_expiry_strength_and_session_invalidation(client: Client) -> None:
    user = account(verified=True)
    client.post(reverse("identity:login"), {"email": user.email, "password": PASSWORD})
    other = Client()
    other.post(reverse("identity:login"), {"email": user.email, "password": PASSWORD})
    client.post(reverse("identity:reset-request"), {"email": user.email})
    token = AccountToken.objects.get()
    assert timedelta(minutes=59) < token.expires_at - token.created_at <= timedelta(hours=1)
    raw = raw_token()
    reset_browser = Client()
    response = reset_browser.get(reverse("identity:reset", args=[raw]))
    assert raw not in response["Location"]
    assert AccountToken.objects.get().consumed_at is None
    weak = reset_browser.post(
        response["Location"], {"password": "123456789012", "password_confirm": "123456789012"}
    )
    assert weak.status_code == 200 and weak.context["form"].errors
    result = reset_browser.post(
        response["Location"], {"password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD}
    )
    assert result["Location"] == reverse("identity:reset-done")
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD) and not user.check_password(PASSWORD)
    assert client.get(reverse("identity:dashboard")).status_code == 302
    assert other.get(reverse("identity:dashboard")).status_code == 302
    reset_browser.get(reverse("identity:reset", args=[raw]))
    assert (
        reset_browser.post(
            reverse("identity:reset-confirm"),
            {
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
        ).status_code
        == 400
    )


def test_reset_does_not_verify_account() -> None:
    user = account()
    request_token(user.email, "reset")
    assert consume_token(token_digest(raw_token()), "reset", NEW_PASSWORD)
    user.refresh_from_db()
    assert user.email_verified_at is None


def test_sensitive_posts_require_csrf() -> None:
    browser = Client(enforce_csrf_checks=True)
    for route in (
        "signup",
        "login",
        "resend",
        "reset-request",
        "verify-confirm",
        "reset-confirm",
        "logout",
    ):
        assert browser.post(reverse("identity:" + route), {}).status_code == 403
    assert not User.objects.exists()


def test_token_confirmation_has_no_cache_and_no_referrer(client: Client) -> None:
    signup(client)
    raw = raw_token()
    response = client.get(reverse("identity:verify", args=[raw]), follow=True)
    assert response["Cache-Control"] == "no-store"
    assert response["Referrer-Policy"] == "same-origin"
    assert raw not in response.content.decode()
    assert token_digest(raw) not in response.content.decode()


def test_outbox_retry_keeps_committed_account_then_clears_sensitive_payload() -> None:
    register("alice@example.test", "Alice", PASSWORD)
    raw = raw_token()
    with patch("django.core.mail.EmailMessage.send", side_effect=OSError("private smtp details")):
        assert send_due() == 1
    item = EmailOutbox.objects.get()
    assert item.status == "pending" and item.attempts == 1 and item.encrypted_payload
    assert User.objects.count() == 1
    assert item.next_attempt_at > timezone.now()
    EmailOutbox.objects.update(next_attempt_at=timezone.now())
    assert send_due() == 1
    item.refresh_from_db()
    assert item.status == "sent" and item.attempts == 2 and item.encrypted_payload == ""
    assert raw in mail.outbox[-1].body
    assert send_due() == 0


def test_outbox_skips_revoked_or_expired_messages() -> None:
    user = account()
    request_token(user.email, "verify")
    request_token(user.email, "verify")
    assert send_due() == 2
    assert EmailOutbox.objects.filter(status="discarded").count() == 1
    assert EmailOutbox.objects.filter(status="sent").count() == 1


def test_rate_limit_applies_to_email_across_ips_and_ignores_spoofed_forwarded_header() -> None:
    factory = RequestFactory()
    with patch.dict("muqola.identity.ratelimit.LIMITS", {"login": (900, 3, 2)}):
        assert allowed(factory.post("/", REMOTE_ADDR="127.0.0.1"), "login", "a@example.test")
        assert allowed(factory.post("/", REMOTE_ADDR="127.0.0.2"), "login", "A@example.test")
        assert not allowed(factory.post("/", REMOTE_ADDR="127.0.0.3"), "login", "a@example.test")
        request = factory.post("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="fake")
        assert allowed(request, "login", "b@example.test")
        assert allowed(request, "login", "c@example.test")
        assert not allowed(request, "login", "d@example.test")
    assert all(
        "example" not in bucket.key and "127.0" not in bucket.key
        for bucket in RateBucket.objects.all()
    )


@pytest.mark.parametrize("route", ["signup", "login", "resend", "reset-request"])
def test_public_forms_are_rate_limited(client: Client, route: str) -> None:
    with patch.dict(
        "muqola.identity.ratelimit.LIMITS",
        {"signup": (900, 1, 1), "login": (900, 1, 1), "resend": (900, 1, 1), "reset": (900, 1, 1)},
    ):
        assert client.post(
            reverse("identity:" + route), {"email": "a@example.test"}
        ).status_code in {200, 302}
        response = client.post(reverse("identity:" + route), {"email": "a@example.test"})
        assert response.status_code == 429 and "Retry-After" in response


def test_ephemeral_records_are_purged() -> None:
    user = account()
    request_token(user.email, "verify")
    AccountToken.objects.update(
        created_at=timezone.now() - timedelta(days=4), expires_at=timezone.now() - timedelta(days=2)
    )
    RateBucket.objects.create(key="f" * 64, expires_at=timezone.now() - timedelta(days=1))
    purge_ephemeral_data()
    assert not AccountToken.objects.exists() and not EmailOutbox.objects.exists()
    assert not RateBucket.objects.exists() and User.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_verifications_can_consume_token_only_once() -> None:
    user = account()
    request_token(user.email, "verify")
    digest = token_digest(raw_token())
    barrier = Barrier(2)

    def attempt() -> bool:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return consume_token(digest, "verify")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [False, True]


@pytest.mark.django_db(transaction=True)
def test_rate_limit_is_atomic_between_workers() -> None:
    barrier = Barrier(4)

    def attempt() -> bool:
        close_old_connections()
        try:
            request = RequestFactory().post("/", REMOTE_ADDR="127.0.0.1")
            barrier.wait(timeout=10)
            return allowed(request, "login", "alice@example.test")
        finally:
            connections.close_all()

    with (
        patch.dict("muqola.identity.ratelimit.LIMITS", {"login": (900, 2, 2)}),
        ThreadPoolExecutor(max_workers=4) as executor,
    ):
        results = list(executor.map(lambda _: attempt(), range(4)))
    assert sum(results) == 2


@override_settings(ROOT_URLCONF="tests.protected_urls")
def test_future_routes_are_protected_by_default(client: Client) -> None:
    assert client.get("/future-business/").status_code == 302
    user = account()
    client.force_login(user)
    assert client.get("/future-business/").status_code == 403
    user.is_superuser = True
    user.save()
    assert client.get("/future-business/").status_code == 403
    user.email_verified_at = timezone.now()
    user.save()
    assert client.get("/future-business/").status_code == 200


def test_renewing_reset_invalidates_previous_link() -> None:
    user = account(verified=True)
    request_token(user.email, "reset")
    old = raw_token()
    request_token(user.email, "reset")
    assert not consume_token(token_digest(old), "reset", NEW_PASSWORD)
    assert consume_token(token_digest(raw_token()), "reset", NEW_PASSWORD)


@pytest.mark.django_db(transaction=True)
def test_concurrent_signup_preserves_unique_account_and_single_email() -> None:
    barrier = Barrier(2)

    def attempt() -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            register("alice@example.test", "Alice", PASSWORD)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: attempt(), range(2)))
    assert User.objects.count() == AccountToken.objects.count() == EmailOutbox.objects.count() == 1


def test_exhausted_ip_does_not_create_unbounded_email_buckets() -> None:
    request = RequestFactory().post("/", REMOTE_ADDR="127.0.0.1")
    with patch.dict("muqola.identity.ratelimit.LIMITS", {"login": (900, 1, 100)}):
        assert allowed(request, "login", "first@example.test")
        count = RateBucket.objects.count()
        for i in range(5):
            assert not allowed(request, "login", f"other-{i}@example.test")
        assert RateBucket.objects.count() == count


def test_signup_cannot_assign_privileges_or_verification(client: Client) -> None:
    client.post(
        reverse("identity:signup"),
        {
            "email": "alice@example.test",
            "display_name": "Alice",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "is_staff": True,
            "is_superuser": True,
            "email_verified_at": "2026-11-01T00:00:00Z",
        },
    )
    user = User.objects.get()
    assert not user.is_staff and not user.is_superuser and user.email_verified_at is None


@override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
def test_login_response_cookies_have_secure_attributes(client: Client) -> None:
    user = account(verified=True)
    response = client.post(
        reverse("identity:login"), {"email": user.email, "password": PASSWORD}, secure=True
    )
    cookie = response.cookies["sessionid"]
    assert cookie["secure"] and cookie["httponly"] and cookie["samesite"] == "Lax"
    assert response.cookies["csrftoken"]["secure"]
