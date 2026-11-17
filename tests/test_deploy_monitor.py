"""Probe failures produce operator codes, never raw application log contents."""

import json
import shutil
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deploy import monitor
from deploy.common import atomic_json, utcnow


def test_monitor_detects_every_required_failure_without_disclosing_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = tmp_path / "backup.json"
    atomic_json(status, {"ok": False, "last_success": "2000-01-01T00:00:00+00:00"})
    monkeypatch.setattr(monitor, "compose", lambda _: ["synthetic-compose"])
    monkeypatch.setattr(
        monitor, "urlopen", lambda *_args, **_kwargs: nullcontext(SimpleNamespace(status=503))
    )
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _: SimpleNamespace(free=1, used=999, total=1000)
    )

    def command(arguments: list[str]) -> bytes:
        if "ps" in arguments:
            return json.dumps(
                [{"Service": "web", "State": "running", "Health": "healthy"}]
            ).encode()
        if "check_operations" in arguments:
            return b'{"database": true, "outbox_failed": 1, "outbox_late": 1}'
        return b'{"level":"ERROR","private":"never-disclose@example.test"}'

    monkeypatch.setattr(monitor, "run", command)
    issues = monitor.inspect(
        {
            "app_url": "https://synthetic.example.test",
            "data_path": str(tmp_path),
            "backup_status_file": str(status),
        }
    )
    assert set(issues) == {
        "https_unavailable",
        "worker_unhealthy",
        "db_unhealthy",
        "database_or_outbox_attention",
        "disk_pressure",
        "backup_failed_or_stale",
        "application_errors",
    }
    assert "never-disclose" not in json.dumps(issues)


def test_monitor_accepts_healthy_stack_and_fresh_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = tmp_path / "backup.json"
    atomic_json(status, {"ok": True, "last_success": utcnow().isoformat()})
    monkeypatch.setattr(monitor, "compose", lambda _: ["synthetic-compose"])
    monkeypatch.setattr(
        monitor, "urlopen", lambda *_args, **_kwargs: nullcontext(SimpleNamespace(status=200))
    )
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=10**10, used=10**9, total=11 * 10**9),
    )

    def command(arguments: list[str]) -> bytes:
        if "ps" in arguments:
            return b"\n".join(
                json.dumps({"Service": service, "State": "running", "Health": "healthy"}).encode()
                for service in ("web", "worker", "db")
            )
        if "check_operations" in arguments:
            return b'{"database": true, "outbox_failed": 0, "outbox_late": 0}'
        return b'{"level":"INFO"}\nnot-json'

    monkeypatch.setattr(monitor, "run", command)
    config: dict[str, Any] = {
        "app_url": "https://synthetic.example.test",
        "data_path": str(tmp_path),
        "backup_status_file": str(status),
    }
    assert monitor.inspect(config) == []
    status.unlink()
    assert monitor.inspect(config) == ["backup_missing"]
