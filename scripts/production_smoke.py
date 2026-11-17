"""Exercise real production containers, roles and encrypted restore, synthetic only.

Requires Docker Compose >=2.24, age and rclone. Never uses the development stack,
ACME, public DNS, external SMTP or a real backup remote. Retains all volumes.
"""

# ruff: noqa: S101 -- executable integration test, assertions are intended

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = "caddy:2.11.9@sha256:f971688b2aaf1a26d256de552f17fb13f64fc5ed2dee4cf40c7f9d70cea0e12d"


def run(args, *, data=None, ok=True, timeout=300):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)  # noqa: S603
    if ok and result.returncode:
        # Only synthetic values exist in this isolated test, but avoid dumping
        # container environments and private keys even in test diagnostics.
        raise RuntimeError(
            f"synthetic command failed: {args[0]}: " + result.stderr.decode()[-1500:]
        )
    return result


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="muqola:local")
    args = parser.parse_args()
    project = "muqola-lot6-synthetic-" + uuid4().hex[:12]
    os.umask(0o077)
    (ROOT / "work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=project + "-", dir=ROOT / "work") as temporary:
        directory = Path(temporary)
        secret_dir = directory / "secrets"
        legal_dir = directory / "legal"
        secret_dir.mkdir()
        legal_dir.mkdir()
        for name in (
            "django_key",
            "db_admin_password",
            "db_migrate_password",
            "db_app_password",
            "smtp_password",
        ):
            path = secret_dir / name
            path.write_text(secrets.token_urlsafe(64))
            # Parent directory is 0700; individual bind mounts must be readable
            # by both the postgres and unprivileged application container UIDs.
            path.chmod(0o444)
        for name in ("mentions", "terms", "privacy", "support"):
            path = legal_dir / (name + ".txt")
            path.write_text("Synthetic test only. Not real legal information. Adults 18+.")
            path.chmod(0o444)
        legal_dir.chmod(0o755)
        env = directory / "production.env"
        values = dict(
            line.split("=", 1)
            for line in (ROOT / ".env.production.example").read_text().splitlines()
            if line and not line.startswith("#")
        )
        values.update(
            MUQOLA_IMAGE=args.image,
            APP_DOMAIN="muqola.example.test",
            MUQOLA_PROJECT=project,
            TRUSTED_PROXY_IPS="127.0.0.1",
            SECRETS_DIR=str(secret_dir),
            LEGAL_DOCUMENTS_DIR=str(legal_dir),
            LEGAL_REVIEWED="true",
        )
        env.write_text("\n".join(key + "=" + value for key, value in values.items()) + "\n")
        env.chmod(0o600)
        base = ["docker", "compose", "--env-file", str(env), "-f", str(ROOT / "compose.prod.yaml")]
        config = json.loads(
            run([*base, "--profile", "maintenance", "config", "--format", "json"]).stdout
        )
        config["name"] = project
        # Explicit volume names from `config` must also be isolated.
        for name, volume in config["volumes"].items():
            volume["name"] = project + "_" + name
        port = free_port()
        domain = values["APP_DOMAIN"]
        for service in ("web", "worker", "migrate"):
            config["services"][service]["environment"]["APP_BASE_URL"] = f"https://{domain}:{port}"
        network = project + "-proxy"
        run(["docker", "network", "create", network])
        info = json.loads(run(["docker", "network", "inspect", network]).stdout)[0]
        subnet = ipaddress.ip_network(info["IPAM"]["Config"][0]["Subnet"])
        caddy_ip = str(subnet.network_address + 10)
        config["networks"]["proxy"]["name"] = network
        config["networks"]["private"]["name"] = project + "_private"
        for service in ("web", "worker", "migrate"):
            config["services"][service]["environment"]["TRUSTED_PROXY_IPS"] = caddy_ip
        proxy_dir = directory / "proxy-config"
        proxy_dir.mkdir(mode=0o755)
        proxy_dir.chmod(0o755)
        fragment = (ROOT / "deploy/Caddyfile").read_text()
        marker = "muqola.tlam.art {"
        assert fragment.count(marker) == 1  # Never accidentally contact ACME.
        (proxy_dir / "muqola.caddy").write_text(
            fragment.replace(marker, domain + " {\n tls internal")
        )
        (proxy_dir / "global-options").write_text(
            (ROOT / "deploy/caddy-global-options.example").read_text()
        )
        witness = "witness.example.test"
        proxy_file = proxy_dir / "Caddyfile"
        proxy_text = (
            "{\n admin localhost:2019\n import /etc/caddy/global-options\n}\n"
            "import /etc/caddy/muqola.caddy\n"
            + witness
            + ' {\n tls internal\n respond "witness-v1"\n}\n'
        )
        proxy_file.write_text(proxy_text)
        for path in proxy_dir.iterdir():
            path.chmod(0o644)
        proxy_config = directory / "proxy.json"
        proxy_project = project + "-edge"
        proxy_config.write_text(
            json.dumps(
                {
                    "name": proxy_project,
                    "services": {
                        "caddy": {
                            "image": CADDY_IMAGE,
                            "environment": {
                                "APP_DOMAIN": "unrelated.example.test",
                                "NO_PROXY": "*",
                                "no_proxy": "*",
                            },
                            "networks": {"proxy": {"ipv4_address": caddy_ip}},
                            "ports": [
                                {
                                    "target": 443,
                                    "published": str(port),
                                    "host_ip": "127.0.0.1",
                                    "protocol": "tcp",
                                }
                            ],
                            "volumes": [
                                str(proxy_dir) + ":/etc/caddy:ro",
                                "data:/data",
                                "config:/config",
                            ],
                            "read_only": True,
                            "tmpfs": ["/tmp"],  # noqa: S108 -- isolated container tmpfs
                            "cap_drop": ["ALL"],
                            "mem_limit": "128m",
                        }
                    },
                    "networks": {"proxy": {"external": True, "name": network}},
                    "volumes": {
                        name: {"name": proxy_project + "_" + name} for name in ("data", "config")
                    },
                }
            )
        )
        edge = ["docker", "compose", "-f", str(proxy_config)]
        compose_file = directory / "compose.json"
        compose_file.write_text(json.dumps(config))
        command = ["docker", "compose", "--env-file", str(env), "-f", str(compose_file)]

        def sql(query, database="muqola", role="muqola_admin", ok=True):
            return run(
                [
                    *command,
                    "exec",
                    "-T",
                    "db",
                    "psql",
                    "-XAt",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    role,
                    "-d",
                    database,
                    "-c",
                    query,
                ],
                ok=ok,
            )

        def snapshot(database):
            tables = (
                sql(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
                    database,
                )
                .stdout.decode()
                .splitlines()
            )
            digest = hashlib.sha256()
            for table in tables:
                digest.update(table.encode())
                digest.update(
                    sql(
                        f'SELECT row_to_json(t)::text FROM "{table}" t '  # noqa: S608 -- catalog names
                        "ORDER BY row_to_json(t)::text",
                        database,
                    ).stdout
                )
            return digest.hexdigest()

        try:
            run([*command, "up", "-d", "--wait", "--wait-timeout", "120", "db"])
            run([*command, "run", "--rm", "migrate"])
            run([*command, "up", "-d", "--wait", "--wait-timeout", "120", "web", "worker"])
            run([*edge, "up", "-d"])
            for _attempt in range(30):
                ready = run(
                    [
                        *edge,
                        "exec",
                        "-T",
                        "caddy",
                        "test",
                        "-f",
                        "/data/caddy/pki/authorities/local/root.crt",
                    ],
                    ok=False,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.2)
            ca = directory / "ca.crt"
            ca.write_bytes(
                run(
                    [
                        *edge,
                        "exec",
                        "-T",
                        "caddy",
                        "cat",
                        "/data/caddy/pki/authorities/local/root.crt",
                    ]
                ).stdout
            )
            curl = [
                "curl",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--resolve",
                f"{domain}:{port}:127.0.0.1",
                "--cacert",
                str(ca),
            ]
            headers = run(
                [*curl, "-D", "-", f"https://{domain}:{port}/accounts/signup/"]
            ).stdout.decode()
            if "csrftoken" not in headers:
                raise RuntimeError("Synthetic HTTPS response: " + headers[:600])
            assert "Secure" in headers and "csrftoken" in headers
            assert run([*curl, "--fail", f"https://{domain}:{port}/health/ready/"]).returncode == 0
            # Client forwarding spoof must not turn an HTTPS response insecure.
            spoof = run(
                [
                    *curl,
                    "--fail",
                    "-D",
                    "-",
                    "-H",
                    "X-Forwarded-Proto: http",
                    f"https://{domain}:{port}/accounts/signup/",
                ]
            ).stdout.decode()
            assert "Secure" in spoof
            csrf = run(
                [
                    *curl,
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "-X",
                    "POST",
                    f"https://{domain}:{port}/accounts/signup/",
                ]
            ).stdout
            assert csrf == b"403"
            cookie = re.search(r"csrftoken=([A-Za-z0-9]+)", headers)
            assert cookie is not None
            valid_csrf = run(
                [
                    *curl,
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "-H",
                    "Cookie: csrftoken=" + cookie[1],
                    "-H",
                    f"Origin: https://{domain}:{port}",
                    "--data-urlencode",
                    "csrfmiddlewaretoken=" + cookie[1],
                    f"https://{domain}:{port}/accounts/signup/",
                ]
            ).stdout
            assert valid_csrf == b"200"  # Invalid form, but valid HTTPS CSRF.
            # All spoofed client addresses still consume the same edge-client budget.
            for attempt in range(10):
                limited = run(
                    [
                        *curl,
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code}",
                        "-H",
                        "Cookie: csrftoken=" + cookie[1],
                        "-H",
                        f"Origin: https://{domain}:{port}",
                        "-H",
                        f"X-Real-IP: 198.51.100.{attempt + 1}",
                        "-H",
                        f"X-Forwarded-For: 203.0.113.{attempt + 1}",
                        "--data-urlencode",
                        "csrfmiddlewaretoken=" + cookie[1],
                        f"https://{domain}:{port}/accounts/signup/",
                    ]
                ).stdout
                assert limited == (b"200" if attempt < 9 else b"429")
            witness_curl = [*curl, "--resolve", f"{witness}:{port}:127.0.0.1"]
            witness_url = f"https://{witness}:{port}/"
            assert run([*witness_curl, "--fail", witness_url]).stdout == b"witness-v1"
            observed = []
            first_probe = threading.Event()

            def probe_witness():
                for _ in range(20):
                    result = run([*witness_curl, "--fail", witness_url], ok=False)
                    observed.append((result.returncode, result.stdout))
                    first_probe.set()
                    time.sleep(0.05)

            probe = threading.Thread(target=probe_witness)
            probe.start()
            assert first_probe.wait(timeout=10)
            try:
                proxy_file.write_text(proxy_text.replace("witness-v1", "witness-v2"))
                run(
                    [
                        *edge,
                        "exec",
                        "-T",
                        "caddy",
                        "caddy",
                        "validate",
                        "--config",
                        "/etc/caddy/Caddyfile",
                        "--adapter",
                        "caddyfile",
                    ]
                )
                run(
                    [
                        *edge,
                        "exec",
                        "-T",
                        "caddy",
                        "caddy",
                        "reload",
                        "--config",
                        "/etc/caddy/Caddyfile",
                        "--adapter",
                        "caddyfile",
                    ]
                )
            finally:
                probe.join(timeout=30)
            assert not probe.is_alive() and len(observed) == 20
            assert all(
                code == 0 and body in {b"witness-v1", b"witness-v2"} for code, body in observed
            )
            assert run([*witness_curl, "--fail", witness_url]).stdout == b"witness-v2"
            run([*curl, "--fail", f"https://{domain}:{port}/health/ready/"])
            for forbidden in (
                "CREATE TABLE forbidden(id int)",
                "CREATE SCHEMA forbidden",
                "CREATE EXTENSION hstore",
                "SET ROLE muqola_migrate",
                "DELETE FROM loans_loan",
                "UPDATE django_migrations SET name=name",
            ):
                assert sql(forbidden, role="muqola_app", ok=False).returncode != 0
            fixture = (ROOT / "scripts/production_fixture.py").read_text()

            run(
                [
                    *command,
                    "exec",
                    "-T",
                    "-e",
                    "MUQOLA_SYNTHETIC_TEST=lot6-isolated",
                    "web",
                    "python",
                    "manage.py",
                    "shell",
                ],
                data=fixture.encode(),
            )
            run(
                [
                    *command,
                    "exec",
                    "-T",
                    "worker",
                    "python",
                    "manage.py",
                    "process_outbox",
                    "--once",
                ]
            )
            run([*command, "stop", "worker"])
            before = snapshot("muqola")
            key = directory / "identity.txt"
            run(["age-keygen", "-o", str(key)])
            recipient = run(["age-keygen", "-y", str(key)]).stdout.decode().strip()
            remote = directory / "offsite-synthetic"
            remote.mkdir()
            rclone = directory / "rclone.conf"
            rclone.write_text("[synthetic]\ntype = local\n")
            backup_config = directory / "backup.json"
            backup_config.write_text(
                json.dumps(
                    dict(
                        project=project,
                        compose_file=str(compose_file),
                        compose_env=str(env),
                        rclone_config=str(rclone),
                        remote="synthetic:" + str(remote),
                        recipient=recipient,
                        retention_days=1,
                        keep_min=1,
                        max_restore_bytes=64 * 1024**2,
                        status_file=str(directory / "status.json"),
                        synthetic=True,
                    )
                )
            )
            old = remote / ("20000101T000000Z-" + "0" * 32 + ".dump.age")
            old.write_text("Synthetic retention fixture")
            unrelated = remote / "unrelated.txt"
            unrelated.write_text("Preserve")
            run([sys.executable, "-m", "deploy.backup", "--config", str(backup_config)])
            status = json.loads((directory / "status.json").read_text())
            assert status["ok"] and not old.exists() and unrelated.exists()
            name = status["object"]
            assert (remote / name).read_bytes().startswith(b"age-encryption.org/v1")
            target = "muqola_restore_" + uuid4().hex
            sql(f'CREATE DATABASE "{target}" OWNER muqola_migrate')
            restore = [
                sys.executable,
                "-m",
                "deploy.restore",
                "--config",
                str(backup_config),
                "--object",
                name,
                "--database",
                target,
                "--identity",
                str(key),
            ]
            run(restore)
            assert snapshot(target) == before == snapshot("muqola")
            assert (
                sql("SELECT count(*) FROM loans_loan", target, "muqola_app").stdout.strip() == b"6"
            )
            assert run(restore, ok=False).returncode != 0  # refuses nonempty
            wrong = directory / "wrong-key.txt"
            run(["age-keygen", "-o", str(wrong)])
            assert run([*restore[:-1], str(wrong)], ok=False).returncode != 0
            assert snapshot(target) == before == snapshot("muqola")
            run([*command, "stop", "web"])
            marker = "synthetic-secret-" + uuid4().hex
            run(
                [
                    *curl,
                    "-H",
                    "Cookie: private=" + marker,
                    "-H",
                    "Authorization: Bearer " + marker,
                    f"https://{domain}:{port}/accounts/verify/{marker}/",
                ]
            )
            proxy_logs = run([*edge, "logs", "--no-color", "caddy"]).stdout
            assert marker.encode() not in proxy_logs
            assert b"http.log.error" in proxy_logs
            run([*command, "stop", "db"])
            failure = run(
                [sys.executable, "-m", "deploy.backup", "--config", str(backup_config)], ok=False
            )
            assert failure.returncode != 0
            failed_status = json.loads((directory / "status.json").read_text())
            assert failed_status["ok"] is False
            assert failed_status["last_success"] == status["last_success"]
            assert b"backup_failed" in failure.stdout
            print(
                json.dumps(
                    dict(
                        production_smoke="passed",
                        roles=True,
                        shared_proxy_reload=True,
                        volumes_preserved=True,
                        proxy_errors_redacted=True,
                        tls=True,
                        csrf=True,
                        backup_restore=True,
                        retention=True,
                        wrong_key_refused=True,
                        backup_failure_detected=True,
                        nonempty_restore_refused=True,
                        loan_states_preserved=6,
                    )
                )
            )
        except Exception:
            print(
                run(
                    [*command, "logs", "--no-color", "--tail", "60", "db"], ok=False
                ).stdout.decode(),
                file=sys.stderr,
            )
            raise
        finally:
            # Stop/remove only this test's containers/networks. Never remove volumes.
            assert project.startswith("muqola-lot6-synthetic-")
            run([*command, "down", "--timeout", "10"], ok=False)
            run([*edge, "down", "--timeout", "10"], ok=False)
            run(["docker", "network", "rm", network], ok=False)
            retained = list(config["volumes"].values()) + [
                {"name": proxy_project + "_" + name} for name in ("data", "config")
            ]
            manifest = ROOT / "work" / (project + "-retained-volumes.json")
            manifest.write_text(json.dumps({"project": project, "volumes": retained}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
