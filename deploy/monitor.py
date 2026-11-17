"""Host/systemd probe: HTTPS, containers, outbox, disk, backup age and JSON errors."""

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

from deploy.common import OperationError, compose, config_file, log, run, utcnow


def inspect(config: dict[str, Any]) -> list[str]:
    issues = []
    root = config["app_url"].rstrip("/")
    if urlsplit(root).scheme != "https":
        raise OperationError("https_probe_required")
    try:
        with urlopen(root + "/health/ready/", timeout=5) as response:  # noqa: S310 — operator-owned config
            if response.status != 200:
                issues.append("https_unavailable")
    except OSError:
        issues.append("https_unavailable")
    raw = run([*compose(config), "ps", "--all", "--format", "json"]).decode()
    try:
        containers = json.loads(raw)
    except ValueError:
        containers = [json.loads(line) for line in raw.splitlines() if line]
    if isinstance(containers, dict):
        containers = [containers]
    by_service = {item["Service"]: item for item in containers}
    for service in ("web", "worker", "db"):
        item = by_service.get(service, {})
        if item.get("State") != "running" or item.get("Health") != "healthy":
            issues.append(service + "_unhealthy")
    metrics = json.loads(
        run([*compose(config), "exec", "-T", "web", "python", "manage.py", "check_operations"])
    )
    if not metrics.get("database") or metrics.get("outbox_failed") or metrics.get("outbox_late"):
        issues.append("database_or_outbox_attention")
    disk = shutil.disk_usage(config["data_path"])
    if disk.free < int(config.get("min_free_bytes", 1024**3)) or disk.used / disk.total > float(
        config.get("max_disk_ratio", 0.9)
    ):
        issues.append("disk_pressure")
    try:
        backup = json.loads(Path(config["backup_status_file"]).read_text())
        last = datetime.fromisoformat(backup["last_success"])
        if not backup.get("ok") or not timedelta(0) <= utcnow() - last <= timedelta(
            hours=int(config.get("max_backup_hours", 36))
        ):
            issues.append("backup_failed_or_stale")
    except (OSError, KeyError, ValueError, TypeError):
        issues.append("backup_missing")
    logs = run(
        [
            *compose(config),
            "logs",
            "--no-color",
            "--no-log-prefix",
            "--since",
            "10m",
            "--tail",
            "500",
            "web",
            "worker",
        ]
    )
    for line in logs.decode(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("level") in {"ERROR", "CRITICAL"}:
            issues.append("application_errors")
            break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        issues = inspect(config_file(args.config))
    except (OSError, ValueError, KeyError, TypeError, OperationError):
        issues = ["monitor_probe_failed"]
    print(json.dumps({"issues": issues}))
    log("monitor_failed" if issues else "monitor_succeeded")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
