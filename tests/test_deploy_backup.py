"""Operator configuration/retention/target guards, no remote or production access."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from deploy.backup import expired, validate
from deploy.common import OperationError, atomic_json
from deploy.restore import restore


def test_retention_only_removes_recognized_old_objects_and_keeps_minimum() -> None:
    names = [f"2026010{i}T120000Z-{'a' * 32}.dump.age" for i in range(1, 6)]
    objects = [{"Name": name, "IsDir": False} for name in names]
    objects += [
        {"Name": "unrelated.dump.age", "IsDir": False},
        {"Name": names[0] + ".partial", "IsDir": False},
    ]
    assert expired(objects, 7, 2, datetime(2026, 2, 1, tzinfo=UTC)) == list(reversed(names[:3]))


def test_local_backend_is_only_available_for_synthetic_testing(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("[synthetic]\ntype = local\n")
    config.chmod(0o600)
    values = {
        "remote": "synthetic:/tmp/isolated",
        "recipient": "age1" + "a" * 58,
        "rclone_config": str(config),
    }
    with pytest.raises(OperationError, match="off_host"):
        validate(values)
    validate(values | {"synthetic": True})
    with pytest.raises(OperationError):
        validate(values | {"synthetic": True, "remote": "synthetic:/../elsewhere"})


def test_restore_cannot_target_application_database_or_inject_a_path(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("[synthetic]\ntype = local\n")
    config.chmod(0o600)
    values = {
        "remote": "synthetic:/tmp/isolated",
        "recipient": "age1" + "a" * 58,
        "rclone_config": str(config),
        "synthetic": True,
    }
    for target in ("muqola", "postgres", "muqola_restore_x;DROP DATABASE muqola"):
        with pytest.raises(OperationError, match="isolated_restore"):
            restore(values, "20260101T000000Z-" + "a" * 32 + ".dump.age", target, tmp_path / "key")


def test_status_file_is_atomic_and_private(tmp_path: Path) -> None:
    path = tmp_path / "state" / "backup.json"
    atomic_json(path, {"ok": True})
    assert path.stat().st_mode & 0o077 == 0
    assert not list(path.parent.glob(".status-*"))
