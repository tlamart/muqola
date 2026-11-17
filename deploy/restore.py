"""Authenticated restore ONLY to a separate, empty muqola_restore_* database."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from deploy.backup import NAME, rclone, validate
from deploy.common import OperationError, compose, config_file, log, private_file, run, tool


def restore(config: dict[str, Any], name: str, database: str, identity: Path) -> None:
    validate(config)
    if not NAME.fullmatch(name) or not re.fullmatch(r"muqola_restore_[a-zA-Z0-9_]+", database):
        raise OperationError("isolated_restore_target_required")
    private_file(identity)
    # Authenticate the entire ciphertext before invoking pg_restore. Plaintext
    # exists briefly in an owner-only temporary directory, removed in finally.
    with tempfile.TemporaryDirectory(prefix="muqola-restore-") as directory:
        archive = Path(directory) / "restore.dump"
        download = subprocess.Popen(  # noqa: S603 — fixed executables, argument arrays, private operator config
            rclone(config, "cat", config["remote"].rstrip("/") + "/" + name),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )  # noqa: S603
        decrypted = None
        try:
            decrypted = subprocess.Popen(  # noqa: S603 — fixed executables, argument arrays, private operator config
                [tool("age"), "-d", "-i", str(identity)],
                stdin=download.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )  # noqa: S603
            if download.stdout is not None:
                download.stdout.close()
            size = 0
            limit = int(config.get("max_restore_bytes", 2 * 1024**3))
            if not 1 <= limit <= 8 * 1024**3:
                raise OperationError("restore_size_limit")
            if shutil.disk_usage(directory).free < limit + 100 * 1024**2:
                raise OperationError("restore_disk_space")
            with archive.open("xb") as output:
                archive.chmod(0o600)
                assert decrypted.stdout is not None  # noqa: S101 — requested PIPE
                while chunk := decrypted.stdout.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise OperationError("restore_size_limit")
                    output.write(chunk)
            if decrypted.wait(timeout=60) or download.wait(timeout=60):
                raise OperationError("restore_authentication_failed")
        finally:
            for process in (decrypted, download):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
        with archive.open("rb") as source:
            run(
                [
                    *compose(config),
                    "exec",
                    "-T",
                    "-e",
                    f"RESTORE_DATABASE={database}",
                    "db",
                    "/opt/muqola/restore.sh",
                ],
                stdin=source,
                timeout=3600,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--object", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        restore(config_file(args.config), args.object, args.database, args.identity)
    except (OSError, ValueError, TypeError, KeyError, OperationError, subprocess.SubprocessError):
        log("restore_failed")
        return 1
    log("restore_succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
