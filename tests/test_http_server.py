"""Non-régression sur sockets réelles, pas avec le client de test Django."""

import http.client
import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from config import gunicorn as config
from scripts.http_stability import Server, running_server, silent_connections


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    with running_server(tmp_path / "gunicorn.log") as instance:
        yield instance


def assert_stable(server: Server, workers: list[str]) -> None:
    assert server.process.poll() is None
    assert server.booted_workers() == workers
    assert "WORKER TIMEOUT" not in server.log.read_text()
    assert "no URI read" not in server.log.read_text()


def test_silent_preconnections_do_not_block_http_or_restart_workers(server: Server) -> None:
    workers = server.booted_workers()
    # Plus de connexions silencieuses que de threads : augmenter seulement le
    # pool ne suffirait pas. On franchit le vrai watchdog de 30 s, sans le relever.
    with silent_connections(server, config.workers * config.threads + 4):
        time.sleep(0.2)
        deadline = time.monotonic() + config.timeout + 2
        while time.monotonic() < deadline:
            assert server.request() == 200
            assert_stable(server, workers)
            time.sleep(0.5)
        assert server.request() == 200
        assert_stable(server, workers)


def test_http_keepalive_is_reused_then_closed_when_idle(server: Server) -> None:
    workers = server.booted_workers()
    connection = server.connection()
    try:
        connection.request("GET", "/health/live/")
        response = connection.getresponse()
        assert response.status == 200 and json.loads(response.read()) == {"status": "ok"}
        original_socket = connection.sock
        assert original_socket is not None
        connection.request("GET", "/health/live/")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        assert connection.sock is original_socket
        original_socket.settimeout(config.keepalive + 3)
        assert original_socket.recv(1) == b""  # Expiration normale, pas un worker tué.
    finally:
        connection.close()
    assert_stable(server, workers)


def test_fragmented_request_and_aborted_connection_leave_server_usable(server: Server) -> None:
    workers = server.booted_workers()
    with silent_connections(server, 1) as connections:
        client = connections[0]
        client.sendall(b"GET /health/live/ HTTP/1.1\r\nHost: localhost\r\n")
        assert server.request() == 200
        client.sendall(b"Connection: close\r\n\r\n")
        response = http.client.HTTPResponse(client)
        response.begin()
        assert response.status == 200
        response.read()
        response.close()
    with silent_connections(server, 1) as connections:
        connections[0].sendall(b"GET /health/")
    assert server.request() == 200
    assert_stable(server, workers)
