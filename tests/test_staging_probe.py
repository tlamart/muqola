"""Real local TLS probe: private credentials, proxy bypass and no redirects."""

import base64
import ipaddress
import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from deploy.common import OperationError
from deploy.probe import protected_probe


def test_probe_refuses_insecure_origin_before_loading_credentials(tmp_path: Path) -> None:
    for url in ("http://staging.example.test", "https://user:secret@staging.example.test"):
        with pytest.raises(OperationError, match="https_probe_origin"):
            protected_probe(url, tmp_path / "absent")


def test_credentials_must_be_private(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text('{"username":"synthetic","password":"synthetic-only"}')
    path.chmod(0o644)
    with pytest.raises(OperationError, match="private_file_permissions"):
        protected_probe("https://staging.example.test", path)


def test_tls_probe_authenticates_bypasses_proxy_and_refuses_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "private.key"
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_file.chmod(0o600)
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"username": "synthetic", "password": "private-test-value"}))
    credentials.chmod(0o600)
    seen: list[tuple[str, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append((self.path, self.headers.get("Authorization")))
            if self.path != "/public" and not self.headers.get("Authorization"):
                self.send_response(401)
                self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"https://127.0.0.1:{self.server.server_port}/sink")  # type: ignore[attr-defined]
            else:
                self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    try:
        root = f"https://127.0.0.1:{server.server_port}"
        assert protected_probe(root + "/ready", credentials, ca_file=str(cert_file))
        with pytest.raises(HTTPError) as error:
            protected_probe(root + "/redirect", credentials, ca_file=str(cert_file))
        assert error.value.code == 302
        with pytest.raises(OperationError, match="staging_access_not_private"):
            protected_probe(root + "/public", credentials, ca_file=str(cert_file))
        assert [path for path, _ in seen] == [
            "/ready",
            "/ready",
            "/redirect",
            "/redirect",
            "/public",
        ]
        expected = "Basic " + base64.b64encode(b"synthetic:private-test-value").decode()
        assert [value for _, value in seen] == [None, expected, None, expected, None]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
