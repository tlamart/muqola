"""pg_dump -> age public-key encryption -> off-host rclone, with bounded retention."""

import argparse
import configparser
import fcntl
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from deploy.common import (
    OperationError,
    atomic_json,
    compose,
    config_file,
    log,
    private_file,
    run,
    tool,
    utcnow,
)

NAME = re.compile(r"^(\d{8}T\d{6}Z)-[0-9a-f]{32}\.dump\.age$")


def validate(config: dict[str, Any]) -> None:
    remote = str(config.get("remote", ""))
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*:[A-Za-z0-9_./-]+", remote
    ) or ".." in remote.split(":", 1)[1].split("/"):
        raise OperationError("invalid_remote")
    if not re.fullmatch(r"age1[a-z0-9]{58}", str(config.get("recipient", ""))):
        raise OperationError("invalid_recipient")
    if (
        not 1 <= int(config.get("retention_days", 30)) <= 3650
        or not 1 <= int(config.get("keep_min", 7)) <= 100
    ):
        raise OperationError("invalid_retention")
    path = Path(config["rclone_config"])
    private_file(path)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    backend = parser.get(remote.split(":", 1)[0], "type", fallback="")
    allowed = {"s3", "sftp", "b2", "azureblob", "webdav"}
    if config.get("synthetic") is True:
        allowed.add("local")
    if backend == "sftp":
        known_hosts = parser.get(remote.split(":", 1)[0], "known_hosts_file", fallback="")
        if not known_hosts or not Path(known_hosts).is_file():
            raise OperationError("sftp_host_key_verification_required")
    if backend == "webdav" and not parser.get(
        remote.split(":", 1)[0], "url", fallback=""
    ).startswith("https://"):
        raise OperationError("https_backend_required")
    if parser.get(remote.split(":", 1)[0], "endpoint", fallback="").startswith("http://"):
        raise OperationError("https_backend_required")
    if backend not in allowed:
        raise OperationError("off_host_backend_required")


def rclone(config: dict[str, Any], *arguments: str) -> list[str]:
    return [
        tool("rclone"),
        "--config",
        str(config["rclone_config"]),
        "--contimeout",
        "15s",
        "--timeout",
        "2m",
        "--retries",
        "2",
        *arguments,
    ]


def expired(objects: list[dict[str, Any]], days: int, keep: int, now: datetime) -> list[str]:
    valid = sorted(
        (
            obj["Name"]
            for obj in objects
            if obj.get("IsDir") is False and NAME.fullmatch(obj.get("Name", ""))
        ),
        reverse=True,
    )
    cutoff = now - timedelta(days=days)
    result = []
    for name in valid[keep:]:
        match = NAME.fullmatch(name)
        assert match is not None  # noqa: S101 — filtered just above
        stamp = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=now.tzinfo)
        if stamp < cutoff:
            result.append(name)
    return result


def backup(config: dict[str, Any]) -> str:
    validate(config)
    now = utcnow()
    name = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex + ".dump.age"
    destination = config["remote"].rstrip("/") + "/" + name
    partial = destination + ".partial"
    dump_command = [*compose(config), "exec", "-T", "db", "/opt/muqola/dump.sh"]
    # No plaintext dump is ever written to disk or passed through argv.
    processes: list[subprocess.Popen[bytes]] = []
    try:
        dump = subprocess.Popen(dump_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)  # noqa: S603
        processes.append(dump)
        encrypted = subprocess.Popen(  # noqa: S603 — fixed executables, argument arrays, private operator config
            [tool("age"), "-r", config["recipient"]],
            stdin=dump.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # noqa: S603
        processes.append(encrypted)
        if dump.stdout is not None:
            dump.stdout.close()
        upload = subprocess.Popen(  # noqa: S603 — fixed executables, argument arrays, private operator config
            rclone(config, "rcat", partial),
            stdin=encrypted.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )  # noqa: S603
        processes.append(upload)
        if encrypted.stdout is not None:
            encrypted.stdout.close()
        codes = [process.wait(timeout=3600) for process in reversed(processes)]
        if any(codes):
            raise OperationError("backup_pipeline_failed")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    size = json.loads(run(rclone(config, "lsjson", partial, "--stat")))["Size"]
    if size <= 0:
        raise OperationError("empty_backup")
    run(rclone(config, "moveto", partial, destination))
    objects = json.loads(run(rclone(config, "lsjson", config["remote"], "--files-only")))
    for old in expired(
        objects, int(config.get("retention_days", 30)), int(config.get("keep_min", 7)), now
    ):
        run(rclone(config, "deletefile", config["remote"].rstrip("/") + "/" + old))
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    status: dict[str, Any] = {}
    try:
        config = config_file(args.config)
        path = Path(config["status_file"])
        if path.exists():
            status = json.loads(path.read_text())
        status.update(last_attempt=utcnow().isoformat(), ok=False)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log("backup_already_running")
                return 1
            name = backup(config)
            status.update(ok=True, last_success=utcnow().isoformat(), object=name)
            atomic_json(path, status)
        log("backup_succeeded")
        return 0
    except (OSError, ValueError, TypeError, KeyError, OperationError, subprocess.SubprocessError):
        if "path" in locals():
            atomic_json(path, status | {"ok": False, "last_attempt": utcnow().isoformat()})
        log("backup_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
