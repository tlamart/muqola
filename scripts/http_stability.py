"""Essais HTTP locaux reproductibles sur un vrai Gunicorn et le vrai Django.

Aucune écriture métier. Lance un serveur isolé sur 127.0.0.1, avec les réglages
du Dockerfile. Les logs n'activent jamais le journal des URL/requêtes.
"""

import argparse
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from config import gunicorn as config

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Server:
    process: subprocess.Popen[bytes]
    port: int
    log: Path

    def connection(self, timeout: float = 2) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)

    def request(self, path: str = "/health/live/", timeout: float = 2) -> int:
        connection = self.connection(timeout)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    def booted_workers(self) -> list[str]:
        return re.findall(r"Booting worker with pid: (\d+)", self.log.read_text())


@contextmanager
def running_server(log: Path, *, baseline_sync: bool = False) -> Iterator[Server]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [
        sys.executable,
        "-m",
        "gunicorn",
        "--config=python:config.gunicorn",
        "config.wsgi:application",
        f"--bind=127.0.0.1:{port}",
        "--log-level=info",  # PIDs des workers, jamais les URL ou données métier.
    ]
    if baseline_sync:
        # threads=1 est indispensable : Gunicorn convertit sync+threads>1 en gthread.
        command.extend(["--worker-class=sync", "--threads=1"])
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:
        process = subprocess.Popen(  # noqa: S603 — arguments fixes, serveur local seulement.
            command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        server = Server(process, port, log)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Gunicorn arrêté au démarrage ; consulter {log}")
                try:
                    if server.request() == 200 and len(server.booted_workers()) == config.workers:
                        break
                except OSError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Gunicorn indisponible au démarrage ; consulter {log}")
            yield server
        finally:
            process.terminate()
            try:
                process.wait(timeout=config.graceful_timeout + 5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


@contextmanager
def silent_connections(server: Server, count: int) -> Iterator[list[socket.socket]]:
    connections: list[socket.socket] = []
    try:
        for _ in range(count):
            connections.append(socket.create_connection(("127.0.0.1", server.port), timeout=2))
        yield connections
    finally:
        for connection in connections:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=1200)
    parser.add_argument("--idle-connections", type=int, default=12)
    parser.add_argument("--baseline-sync", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("work/http-stability"))
    args = parser.parse_args()
    if args.duration < 1 or not 1 <= args.idle_connections <= 32:
        parser.error("Durée positive et 1 à 32 connexions silencieuses requises.")
    args.output.mkdir(parents=True, exist_ok=True)
    log = args.output / "gunicorn.log"
    failures: list[dict[str, str | int]] = []
    latencies: list[float] = []
    probes = 0
    started = time.monotonic()
    with running_server(log, baseline_sync=args.baseline_sync) as server:
        initial_workers = server.booted_workers()
        with silent_connections(server, args.idle_connections):
            time.sleep(
                0.2
            )  # Laisser le serveur accepter les connexions, sans leur envoyer d'octet.
            deadline = time.monotonic() + args.duration
            next_progress = time.monotonic() + 60
            while time.monotonic() < deadline:
                for path in ("/health/live/", "/health/ready/", "/", "/accounts/login/"):
                    probe_start = time.monotonic()
                    try:
                        status = server.request(path)
                        if status != 200:
                            failures.append({"path": path, "status": status})
                    except (OSError, http.client.HTTPException) as error:
                        failures.append({"path": path, "error": type(error).__name__})
                    probes += 1
                    latencies.append(time.monotonic() - probe_start)
                # Fermetures abruptes de préconnexions supplémentaires, sans requête.
                with silent_connections(server, 2):
                    pass
                if time.monotonic() >= next_progress:
                    print(json.dumps({"probes": probes, "failures": len(failures)}), flush=True)
                    next_progress = time.monotonic() + 60
                time.sleep(1)
        final_workers = server.booted_workers()
    log_text = log.read_text()
    result = {
        "gunicorn": version("gunicorn"),
        "worker_class": "sync" if args.baseline_sync else config.worker_class,
        "worker_timeout_seconds": config.timeout,
        "duration_requested_seconds": args.duration,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "silent_connections": args.idle_connections,
        "probes": probes,
        "failure_count": len(failures),
        "failure_sample": failures[:20],
        "max_latency_seconds": round(max(latencies, default=0), 4),
        "worker_timeouts": log_text.count("WORKER TIMEOUT"),
        "no_uri_errors": log_text.count("no URI read"),
        "worker_pids_initial": initial_workers,
        "worker_pids_final": final_workers,
        "workers_unchanged": initial_workers == final_workers,
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    return int(bool(failures) or not result["workers_unchanged"] or bool(result["worker_timeouts"]))


if __name__ == "__main__":
    raise SystemExit(main())
