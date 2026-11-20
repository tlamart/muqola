"""Two isolated synthetic stacks, one shared Caddy; never contacts the real VPS.

Retains every volume. HTTPS uses an internal CA and explicit loopback resolution.
"""

# ruff: noqa: S101 -- executable integration assertions

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

from production_smoke import CADDY_IMAGE, ROOT, create_proxy_network, free_port, run


def model(profile, project, directory, image):
    directory.mkdir(mode=0o755)
    secret_dir, legal_dir = directory / "secrets", directory / "legal"
    secret_dir.mkdir(mode=0o700)
    legal_dir.mkdir(mode=0o755)
    legal_dir.chmod(0o755)
    for name in (
        "django_key",
        "db_admin_password",
        "db_migrate_password",
        "db_app_password",
        "smtp_password",
    ):
        path = secret_dir / name
        path.write_text(secrets.token_urlsafe(64))
        path.chmod(0o444)
    for name in ("mentions", "terms", "privacy", "support"):
        path = legal_dir / (name + ".txt")
        path.write_text("Synthetic private test. Not real legal information. Adults 18+.")
        path.chmod(0o444)
    example = ROOT / (".env.staging.example" if profile == "staging" else ".env.production.example")
    values = dict(
        line.split("=", 1)
        for line in example.read_text().splitlines()
        if line and not line.startswith("#")
    )
    values.update(
        MUQOLA_PROJECT=project,
        MUQOLA_IMAGE=image,
        TRUSTED_PROXY_IPS="127.0.0.1",
        SECRETS_DIR=str(secret_dir),
        LEGAL_DOCUMENTS_DIR=str(legal_dir),
        LEGAL_REVIEWED="false" if profile == "staging" else "true",
    )
    env = directory / "environment"
    env.write_text("\n".join(k + "=" + v for k, v in values.items()) + "\n")
    env.chmod(0o600)
    source = ROOT / ("compose.staging.yaml" if profile == "staging" else "compose.prod.yaml")
    rendered = json.loads(
        run(
            [
                "docker",
                "compose",
                "--env-file",
                str(env),
                "-f",
                str(source),
                "--profile",
                "*",
                "config",
                "--format",
                "json",
            ]
        ).stdout
    )
    rendered["name"] = project
    for name, volume in rendered["volumes"].items():
        volume["name"] = project + "_" + name
    rendered["networks"]["private"]["name"] = project + "_private"
    path = directory / "compose.json"
    command = ["docker", "compose", "--env-file", str(env), "-f", str(path)]
    if profile == "staging":
        command += ["--profile", "staging"]
    return rendered, path, command


def shell(command, source):
    return run(
        [
            *command,
            "exec",
            "-T",
            "web",
            "python",
            "manage.py",
            "shell",
            "--verbosity",
            "0",
            "-c",
            source,
        ]
    ).stdout


def sql(command, database, query):
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
            "muqola_admin",
            "-d",
            database,
            "-c",
            query,
        ]
    ).stdout


def snapshot(command, database):
    tables = (
        sql(
            command,
            database,
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
        )
        .decode()
        .splitlines()
    )
    digest = hashlib.sha256()
    for table in tables:
        digest.update(table.encode())
        digest.update(
            sql(
                command,
                database,
                f'SELECT row_to_json(t)::text FROM "{table}" t '  # noqa: S608 -- catalog names
                "ORDER BY row_to_json(t)::text",
            )
        )  # noqa: S608 -- database catalog names
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="muqola:local")
    parser.add_argument("--exercise-release", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    prefix = "muqola-stage-synthetic-" + secrets.token_hex(6)
    (ROOT / "work").mkdir(exist_ok=True)
    peak_memory = peak_cpu = 0.0
    samples = 0
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
    metrics_valid = bool(
        info.get("MemoryLimit") and info.get("CpuCfsQuota") and info.get("CgroupDriver") != "none"
    )
    stop = threading.Event()
    with tempfile.TemporaryDirectory(prefix=prefix, dir=ROOT / "work") as temp:
        directory = Path(temp)
        production, prod_path, prod = model(
            "production", prefix + "-prod", directory / "production", args.image
        )
        staging, stage_path, stage = model(
            "staging", prefix + "-stage", directory / "staging", args.image
        )
        network = prefix + "-proxy"
        peer = create_proxy_network(network)
        port = free_port()
        stage_host, prod_host = "staging.muqola.tlam.art", "muqola.example.test"
        for document, host in ((production, prod_host), (staging, stage_host)):
            document["networks"]["proxy"]["name"] = network
            for service in ("web", "worker", "migrate"):
                document["services"][service]["environment"].update(
                    TRUSTED_PROXY_IPS=peer,
                    APP_BASE_URL=f"https://{host}:{port}",
                    ALLOWED_HOSTS=host,
                )
        prod_path.write_text(json.dumps(production))
        stage_path.write_text(json.dumps(staging))
        proxy_dir = directory / "proxy"
        proxy_dir.mkdir(mode=0o755)
        proxy_dir.chmod(0o755)
        private_dir = proxy_dir / "private"
        private_dir.mkdir(mode=0o755)
        private_dir.chmod(0o755)
        for source, target, marker, host in (
            ("deploy/Caddyfile", "production.caddy", "muqola.tlam.art {", prod_host),
            ("deploy/Caddyfile.staging", "staging.caddy", "staging.muqola.tlam.art {", stage_host),
        ):
            content = (ROOT / source).read_text()
            assert content.count(marker) == 1
            path = proxy_dir / target
            path.write_text(content.replace(marker, host + " {\n tls internal"))
            path.chmod(0o444)
        global_file = proxy_dir / "global-options"
        global_file.write_text((ROOT / "deploy/caddy-global-options.example").read_text())
        global_file.chmod(0o444)
        proxy_file = proxy_dir / "Caddyfile"
        proxy_file.write_text(
            "{\n admin localhost:2019\n import /etc/caddy/global-options\n}\n"
            "import /etc/caddy/production.caddy\nimport /etc/caddy/staging.caddy\n"
        )
        proxy_file.chmod(0o444)
        edge_path = directory / "edge.json"
        edge_project = prefix + "-edge"
        edge_doc = {
            "name": edge_project,
            "services": {
                "caddy": {
                    "image": CADDY_IMAGE,
                    "environment": {"NO_PROXY": "*", "no_proxy": "*"},
                    "networks": {"proxy": {"ipv4_address": peer}},
                    "ports": [{"target": 443, "published": str(port), "host_ip": "127.0.0.1"}],
                    "volumes": [str(proxy_dir) + ":/etc/caddy:ro", "data:/data", "config:/config"],
                    "mem_limit": "128m",
                    "read_only": True,
                    "tmpfs": ["/tmp"],  # noqa: S108 -- private test container
                    "cap_drop": ["ALL"],
                }
            },
            "networks": {"proxy": {"external": True, "name": network}},
            "volumes": {n: {"name": edge_project + "_" + n} for n in ("data", "config")},
        }
        edge_path.write_text(json.dumps(edge_doc))
        edge = ["docker", "compose", "-f", str(edge_path)]
        username, password = "synthetic-tester", secrets.token_urlsafe(24)
        netrc = directory / "netrc"
        netrc.write_text(f"machine {stage_host} login {username} password {password}\n")
        netrc.chmod(0o600)

        def sample():
            nonlocal peak_memory, peak_cpu, samples
            while metrics_valid and not stop.is_set():
                ids = (
                    run(
                        [
                            "docker",
                            "ps",
                            "--filter",
                            "label=com.docker.compose.project=" + staging["name"],
                            "--format",
                            "{{.ID}}",
                        ],
                        ok=False,
                    )
                    .stdout.decode()
                    .split()
                )
                if ids:
                    result = run(
                        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], ok=False
                    )
                    memory = cpu = 0.0
                    for line in result.stdout.decode().splitlines():
                        item = json.loads(line)
                        value = item["MemUsage"].split("/")[0].strip()
                        match = re.fullmatch(r"([0-9.]+)([kMGT]?i?B)", value)
                        if match:
                            units = {
                                "B": 1 / 1024**2,
                                "kB": 1000 / 1024**2,
                                "KiB": 1 / 1024,
                                "MB": 1000**2 / 1024**2,
                                "MiB": 1,
                                "GiB": 1024,
                                "GB": 1000**3 / 1024**2,
                            }
                            memory += float(match[1]) * units[match[2]]
                        cpu += float(item["CPUPerc"].rstrip("%"))
                    peak_memory, peak_cpu = max(peak_memory, memory), max(peak_cpu, cpu)
                    samples += 1
                stop.wait(0.2)

        sampler = threading.Thread(target=sample)
        try:
            # Hash only this generated synthetic password; no real credential is read.
            hashed = (
                run(
                    [
                        *edge,
                        "run",
                        "--rm",
                        "--no-deps",
                        "caddy",
                        "caddy",
                        "hash-password",
                        "--plaintext",
                        password,
                    ]
                )
                .stdout.decode()
                .strip()
            )
            auth_file = private_dir / "muqola-staging-users"
            auth_file.write_text(username + " " + hashed + "\n")
            auth_file.chmod(0o444)
            run([*prod, "up", "-d", "--no-build", "--wait", "db"])
            run([*prod, "run", "--rm", "migrate"])
            run([*prod, "up", "-d", "--no-build", "--wait", "web", "worker"])
            fixture = (ROOT / "scripts/production_fixture.py").read_bytes()
            run(
                [
                    *prod,
                    "exec",
                    "-T",
                    "-e",
                    "MUQOLA_SYNTHETIC_TEST=lot6-isolated",
                    "web",
                    "python",
                    "manage.py",
                    "shell",
                    "--verbosity",
                    "0",
                ],
                data=fixture,
            )
            before = snapshot(prod, "muqola")
            sampler.start()
            run([*stage, "up", "-d", "--no-build", "--wait", "db", "mailpit"])
            run([*stage, "run", "--rm", "migrate"])
            run([*stage, "up", "-d", "--no-build", "--wait", "web", "worker"])
            run(
                [
                    *edge,
                    "run",
                    "--rm",
                    "--no-deps",
                    "caddy",
                    "caddy",
                    "validate",
                    "--config",
                    "/etc/caddy/Caddyfile",
                    "--adapter",
                    "caddyfile",
                ]
            )
            run([*edge, "up", "-d"])
            ca = directory / "root.crt"
            for _ in range(30):
                result = run(
                    [
                        *edge,
                        "exec",
                        "-T",
                        "caddy",
                        "cat",
                        "/data/caddy/pki/authorities/local/root.crt",
                    ],
                    ok=False,
                )
                if result.returncode == 0:
                    ca.write_bytes(result.stdout)
                    break
                time.sleep(0.2)
            assert ca.is_file(), "Synthetic Caddy did not initialize its local CA"
            curl = [
                "curl",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--cacert",
                str(ca),
                "--resolve",
                f"{stage_host}:{port}:127.0.0.1",
                "--resolve",
                f"{prod_host}:{port}:127.0.0.1",
            ]
            stage_url, prod_url = f"https://{stage_host}:{port}", f"https://{prod_host}:{port}"
            for path in (
                "/",
                "/accounts/signup/",
                "/accounts/login/",
                "/health/ready/",
                "/legal/privacy/",
                "/unknown/",
            ):
                blocked = run([*curl, "-D", "-", stage_url + path]).stdout.decode()
                assert (
                    "401" in blocked.splitlines()[0] and "noindex, nofollow, noarchive" in blocked
                )
            bad_netrc = directory / "bad.netrc"
            bad_netrc.write_text(
                f"machine {stage_host} login {username} password wrong-synthetic-only\n"
            )
            bad_netrc.chmod(0o600)
            denied = run(
                [
                    *curl,
                    "--netrc-file",
                    str(bad_netrc),
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    stage_url + "/health/ready/",
                ]
            ).stdout
            assert denied == b"401"
            authenticated = [*curl, "--netrc-file", str(netrc)]
            closed = run(
                [
                    *authenticated,
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    stage_url + "/accounts/signup/",
                ]
            ).stdout
            assert closed == b"503"  # Legal gate preserved even behind private edge access.
            run([*curl, "--fail", prod_url + "/health/ready/"])
            for name in ("web", "worker", "migrate"):
                staging["services"][name]["environment"]["LEGAL_REVIEWED"] = (
                    "true"  # Synthetic test files only.
                )
            stage_path.write_text(json.dumps(staging))
            run([*stage, "up", "-d", "--no-build", "--wait", "web", "worker"])
            run([*stage, "exec", "-T", "web", "python", "manage.py", "staging_readiness"])
            assert (
                run(
                    [*stage, "exec", "-T", "web", "python", "manage.py", "production_readiness"],
                    ok=False,
                ).returncode
                != 0
            )
            headers = run(
                [*authenticated, "--fail", "-D", "-", stage_url + "/accounts/signup/"]
            ).stdout.decode()
            assert "Secure" in headers and "Domain=" not in headers
            cookie = re.search(r"csrftoken=([A-Za-z0-9]+)", headers)
            assert cookie
            fields = [
                "-H",
                "Cookie: csrftoken=" + cookie[1],
                "-H",
                "Origin: " + stage_url,
                "--data-urlencode",
                "csrfmiddlewaretoken=" + cookie[1],
                "--data-urlencode",
                "email=staging-smoke@example.test",
                "--data-urlencode",
                "display_name=Test fictif",
                "--data-urlencode",
                "password=" + password,
                "--data-urlencode",
                "password_confirm=" + password,
            ]
            assert (
                run(
                    [
                        *authenticated,
                        *fields,
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code}",
                        stage_url + "/accounts/signup/",
                    ]
                ).stdout
                == b"200"
            )  # No adult attestation.
            assert (
                run(
                    [
                        *authenticated,
                        *fields,
                        "--data-urlencode",
                        "adult_confirmed=on",
                        "-o",
                        "/dev/null",
                        "-w",
                        "%{http_code}",
                        stage_url + "/accounts/signup/",
                    ]
                ).stdout
                == b"302"
            )
            for _ in range(30):
                count = shell(
                    stage,
                    "from muqola.notifications.models import EmailOutbox; "
                    'print(EmailOutbox.objects.filter(status="sent").count())',
                )
                if count.strip() == b"1":
                    break
                time.sleep(0.3)
            assert count.strip() == b"1"
            captured = shell(
                stage,
                "import json; from urllib.request import urlopen; "
                'value=json.load(urlopen("http://mailpit:8025/api/v1/messages")); '
                'print(value["total"])',
            )
            assert int(captured.strip()) == 1
            assert sql(prod, "muqola", "SELECT count(*) FROM identity_user").strip() == b"2"
            assert (
                sql(stage, "muqola_staging", "SELECT count(*) FROM identity_user").strip() == b"1"
            )
            private_network = staging["networks"]["private"]["name"]
            assert json.loads(run(["docker", "network", "inspect", private_network]).stdout)[0][
                "Internal"
            ]
            for service in ("db", "worker", "mailpit"):
                cid = run([*stage, "ps", "-q", service]).stdout.decode().strip()
                actual = json.loads(run(["docker", "inspect", cid]).stdout)[0]
                assert set(actual["NetworkSettings"]["Networks"]) == {private_network}
            # Refuse a real-transport configuration before any mail delivery can start.
            unsafe = run(
                [
                    *stage,
                    "exec",
                    "-T",
                    "-e",
                    "EMAIL_HOST=smtp.example.test",
                    "worker",
                    "python",
                    "manage.py",
                    "check",
                ],
                ok=False,
            )
            assert unsafe.returncode != 0
            for _ in range(2):
                run([*stage, "stop", "--timeout", "10", "web", "worker", "mailpit", "db"])
                run([*curl, "--fail", prod_url + "/health/ready/"])
                assert snapshot(prod, "muqola") == before
                run([*stage, "up", "-d", "--no-build", "--wait", "db", "mailpit", "web", "worker"])
                run([*authenticated, "--fail", stage_url + "/health/ready/"])
                assert (
                    sql(stage, "muqola_staging", "SELECT count(*) FROM identity_user").strip()
                    == b"1"
                )
            if args.exercise_release:
                release_stop = threading.Event()
                release_probes = []

                def witness_during_release():
                    while not release_stop.is_set():
                        response = run(
                            [*curl, "--max-time", "3", "--fail", prod_url + "/health/ready/"],
                            ok=False,
                        )
                        release_probes.append(response.returncode == 0)
                        release_stop.wait(0.3)

                witness = threading.Thread(target=witness_during_release)
                witness.start()
                try:
                    release_result = run(
                        [
                            sys.executable,
                            "-m",
                            "scripts.release_smoke",
                            "--compose-file",
                            str(stage_path),
                            "--compose-env",
                            str(directory / "staging" / "environment"),
                            "--url",
                            stage_url,
                            "--cacert",
                            str(ca),
                            "--netrc",
                            str(netrc),
                        ],
                        timeout=900,
                    )
                finally:
                    release_stop.set()
                    witness.join(timeout=5)
                assert not witness.is_alive() and release_probes and all(release_probes)
                print(release_result.stdout.decode().strip())
                assert snapshot(prod, "muqola") == before
            run([*stage, "stop", "--timeout", "10", "web"])
            marker = "synthetic-private-" + secrets.token_hex(16)
            run(
                [
                    *authenticated,
                    "-H",
                    "Cookie: private=" + marker,
                    stage_url + "/accounts/verify/" + marker + "/",
                ]
            )
            logs = run([*edge, "logs", "--no-color", "caddy"]).stdout
            assert marker.encode() not in logs and password.encode() not in logs
            assert snapshot(prod, "muqola") == before
            result = {
                "staging_smoke": "passed",
                "private_access": True,
                "noindex": True,
                "capture_only": True,
                "production_unchanged": True,
                "restart_persistence": True,
                "volumes_preserved": True,
                "sampled_peak_memory_mib": round(peak_memory, 2) if metrics_valid else None,
                "sampled_peak_cpu_percent": round(peak_cpu, 2) if metrics_valid else None,
                "measurement_valid": metrics_valid,
                "measurement_reason": "cgroup_samples"
                if metrics_valid
                else "docker_cgroups_unavailable",
                "samples": samples,
                "host_cpu_count": os.cpu_count(),
                "vps_capacity_validated": False,
            }
            (ROOT / "work/staging-smoke.json").write_text(json.dumps(result))
            print(json.dumps(result))
        finally:
            stop.set()
            if sampler.is_alive():
                sampler.join(timeout=15)
            for command in (stage, prod, edge):
                run([*command, "down", "--timeout", "10"], ok=False)
            run(["docker", "network", "rm", network], ok=False)
            retained = [
                v for doc in (staging, production, edge_doc) for v in doc["volumes"].values()
            ]
            (ROOT / "work" / (prefix + "-retained-volumes.json")).write_text(json.dumps(retained))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
