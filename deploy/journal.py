"""Opt-in Docker syslog transport to an existing, isolated systemd journal namespace.

No daemon-wide settings, access logs, docker-managed file edits or implicit install.
"""

from pathlib import Path
from typing import Any

from deploy.common import OperationError


def namespace(config: dict[str, Any]) -> str:
    value = config.get("journal_namespace")
    expected = "muqola-" + config.get("environment", "production")
    if value != expected or value not in {"muqola-production", "muqola-staging"}:
        raise OperationError("isolated_journal_namespace_required")
    return str(value)


def apply_logging(document: dict[str, Any], config: dict[str, Any]) -> None:
    if "journal_namespace" not in config:
        return
    name = namespace(config)
    socket = Path("/run/systemd/journal." + name + "/dev-log")
    if not socket.is_socket():
        raise OperationError("journal_namespace_socket_required_before_plan")
    for service_name, service in document["services"].items():
        service["logging"] = {
            "driver": "syslog",
            "options": {
                "syslog-address": "unixgram://" + str(socket),
                "syslog-format": "rfc3164",
                "tag": config["project"] + "-" + service_name,
                # Docker's local dual-logging cache otherwise outlives the journal.
                "cache-disabled": "true",
            },
        }


def error_log_command(config: dict[str, Any]) -> list[str]:
    name = namespace(config)
    return [
        "journalctl",
        "--namespace=" + name,
        "--no-pager",
        "--since=10min",
        "--output=json",
        "--lines=500",
        "SYSLOG_IDENTIFIER=" + config["project"] + "-web",
        "SYSLOG_IDENTIFIER=" + config["project"] + "-worker",
    ]
