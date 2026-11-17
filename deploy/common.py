"""Small, dependency-free host helpers. Errors never include command arguments."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class OperationError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def private_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise OperationError("private_file_permissions")


def config_file(path: Path) -> dict[str, Any]:
    private_file(path)
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise OperationError("invalid_configuration") from error
    if not isinstance(value, dict):
        raise OperationError("invalid_configuration")
    return value


def tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise OperationError("missing_tool_" + name)
    return executable


def run(arguments: list[str], *, stdin: Any = None, timeout: int = 300) -> bytes:
    try:
        result = subprocess.run(  # noqa: S603 — fixed commands, private config, no shell
            arguments, stdin=stdin, capture_output=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationError("command_unavailable_or_timed_out") from error
    if result.returncode:
        raise OperationError("command_failed")
    return result.stdout


def compose(config: dict[str, Any]) -> list[str]:
    env = Path(config["compose_env"])
    private_file(env)
    project = str(config.get("project", ""))
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise OperationError("explicit_compose_project_required")
    return [
        tool("docker"),
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env),
        "-f",
        str(config["compose_file"]),
    ]


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".status-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def log(event: str) -> None:
    print(json.dumps({"timestamp": utcnow().isoformat(), "event": event}), flush=True)
