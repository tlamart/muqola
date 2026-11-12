import json
import logging
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import Client, override_settings

from muqola.core.logging import SafeJsonFormatter

SOURCE = str(Path(__file__).resolve().parents[1] / "muqola/core/views.py")


def record(message: object = "unexpected") -> logging.LogRecord:
    result = logging.LogRecord("muqola.core.views", logging.ERROR, SOURCE, 42, message, (), None)
    result.funcName = "health_ready"
    result.created = 1794474000.125
    return result


def test_allowed_diagnostics_and_valid_json() -> None:
    payload = json.loads(SafeJsonFormatter().format(record()))
    assert payload == {
        "level": "ERROR",
        "logger": "muqola.core.views",
        "event": "runtime_event",
        "timestamp": "2026-11-12T09:00:00.125Z",
        "module": "muqola.core.views",
        "function": "health_ready",
        "line": 42,
    }
    assert datetime.fromisoformat(payload["timestamp"]).tzinfo == UTC


@pytest.mark.parametrize(
    "event", ["database_unavailable", "notification_retry", "notification_failed"]
)
def test_known_business_events(event: str) -> None:
    payload = json.loads(SafeJsonFormatter().format(record(event)))
    assert payload["event"] == event
    assert "exception_type" not in payload


@pytest.mark.parametrize("exception", [ValueError, RuntimeError])
def test_application_exception_discards_all_sensitive_content(exception: type[Exception]) -> None:
    secret = "token=fictif cookie=session-fictive alice@example.test +33123456789"
    item = record("https://example.test/invite/fictif/?token=%s")
    item.args = (secret,)
    try:
        raise exception(secret)
    except exception:
        item.exc_info = sys.exc_info()
    item.exc_text = secret
    item.stack_info = secret
    item.request = {"body": secret, "cookies": secret, "headers": secret}
    item.correlation_id = secret
    item.email = secret
    output = SafeJsonFormatter().format(item)
    payload = json.loads(output)
    assert payload["exception_type"] == exception.__name__
    assert payload["module"] == "muqola.core.views"
    assert set(payload) == {
        "level",
        "logger",
        "event",
        "timestamp",
        "exception_type",
        "module",
        "function",
        "line",
    }
    for value in (secret, "alice", "fictif", "Traceback", "request", "exc_text", "stack_info"):
        assert value not in output


def test_untrusted_message_is_never_formatted() -> None:
    class Sensitive:
        def __str__(self) -> str:
            raise AssertionError("Must not stringify message or arguments")

    item = record(Sensitive())
    item.args = (Sensitive(),)
    assert json.loads(SafeJsonFormatter().format(item))["event"] == "runtime_event"


def test_external_location_drops_absolute_path_and_function() -> None:
    item = record()
    item.pathname = "/home/alice@example.test/private.py"
    item.funcName = "sensitive"
    payload = json.loads(SafeJsonFormatter().format(item))
    assert set(payload) == {"level", "logger", "event", "timestamp"}


@override_settings(DEBUG_PROPAGATE_EXCEPTIONS=False)
def test_real_django_exception_uses_application_frame_without_traceback(client: Client) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter())
    logger = logging.getLogger("django.request")
    # Une vraie exception applicative via Django, sans créer de route de diagnostic.
    with (
        patch.object(logger, "handlers", [handler]),
        patch("muqola.core.views.connection.cursor", side_effect=ValueError("alice@example.test")),
        pytest.raises(ValueError),
    ):
        client.get("/health/ready/?token=fictif", HTTP_COOKIE="synthetic=fictif")
    payload = json.loads(stream.getvalue())
    assert payload["exception_type"] == "ValueError"
    assert payload["module"] == "muqola.core.views"
    assert payload["function"] == "health_ready"
    assert isinstance(payload["line"], int)
    assert "alice" not in stream.getvalue()
    assert "fictif" not in stream.getvalue()
    assert "Traceback" not in stream.getvalue()


@pytest.mark.parametrize("filename", ["", "/external/private.py", "<string>"])
def test_missing_or_external_location_is_optional(filename: str) -> None:
    item = record()
    item.pathname = filename
    assert set(json.loads(SafeJsonFormatter().format(item))) == {
        "level",
        "logger",
        "event",
        "timestamp",
    }


def test_exception_locals_and_chained_messages_are_not_inspected() -> None:
    class SensitiveLocal:
        def __repr__(self) -> str:
            raise AssertionError("Must not inspect locals")

    private_local = SensitiveLocal()
    assert private_local is not None
    item = record()
    try:
        try:
            raise ValueError("token=fictif")
        except ValueError as cause:
            raise RuntimeError("alice@example.test") from cause
    except RuntimeError:
        item.exc_info = sys.exc_info()
    payload = json.loads(SafeJsonFormatter().format(item))
    assert payload["exception_type"] == "RuntimeError"
    assert "ValueError" not in json.dumps(payload)
    assert "alice" not in json.dumps(payload)
    assert "fictif" not in json.dumps(payload)
