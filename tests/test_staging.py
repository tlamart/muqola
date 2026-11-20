"""Staging guards: no production credentials/data/SMTP and safe lifecycle admission."""

import copy
import fcntl
import json
import shutil
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import Client, override_settings

from deploy import staging as lifecycle
from deploy.check_config import validate
from deploy.common import OperationError, atomic_json
from deploy.staging_config import isolation_issues
from muqola.identity.forms import SignupForm
from muqola.identity.models import User
from muqola.identity.services import register

ROOT = Path(__file__).resolve().parents[1]


def render(tmp_path: Path, environment: str) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose needed")
    example = ROOT / (
        ".env.staging.example" if environment == "staging" else ".env.production.example"
    )
    value = (
        example.read_text()
        .replace("REPLACE_WITH_64_HEX_DIGEST", "a" * 64)
        .replace("REPLACE_WITH_CADDY_CONTAINER_IP", "192.0.2.10")
    )
    env = tmp_path / (environment + ".env")
    env.write_text(value)
    env.chmod(0o600)
    filename = "compose.staging.yaml" if environment == "staging" else "compose.prod.yaml"
    response = subprocess.run(  # noqa: S603 -- read-only fixed Compose
        [
            docker,
            "compose",
            "--env-file",
            str(env),
            "-f",
            str(ROOT / filename),
            "--profile",
            "*",
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return json.loads(response.stdout)  # type: ignore[no-any-return]


@pytest.fixture
def profiles(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return render(tmp_path, "production"), render(tmp_path, "staging")


def test_profiles_are_isolated_with_security_preserved(
    profiles: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    prod, stage = profiles
    assert validate(prod, "muqola-prod") == []
    assert validate(stage, "muqola-staging", environment="staging") == []
    assert isolation_issues(prod, stage) == []
    assert stage["networks"]["private"]["internal"]
    assert not any(s.get("ports") or s.get("build") for s in stage["services"].values())
    assert stage["services"]["web"]["environment"]["APP_ENV"] == "production"
    assert stage["services"]["worker"]["environment"]["EMAIL_HOST_USER"] == ""
    assert "smtp_password" not in stage["secrets"]
    assert (
        sum(int(s["mem_limit"]) for n, s in stage["services"].items() if n != "migrate")
        == 832 * 1024**2
    )
    for name in ("web", "worker", "migrate"):
        assert stage["services"][name]["read_only"]
        assert stage["services"][name]["cap_drop"] == ["ALL"]
        assert "db_admin_password" not in {s["source"] for s in stage["services"][name]["secrets"]}


@pytest.mark.parametrize("fault", ["smtp", "network", "project", "volume", "database", "relay"])
def test_unsafe_staging_configuration_is_rejected(
    profiles: tuple[dict[str, Any], dict[str, Any]], fault: str
) -> None:
    _, stage = profiles
    if fault == "smtp":
        stage["services"]["worker"]["environment"]["EMAIL_HOST"] = "smtp.example.test"
    if fault == "network":
        stage["networks"]["private"]["internal"] = False
    if fault == "project":
        stage["name"] = "muqola-prod"
    if fault == "volume":
        stage["volumes"]["postgres_data"]["name"] = "muqola-prod_postgres_data"
    if fault == "database":
        stage["services"]["db"]["environment"]["POSTGRES_DB"] = "muqola"
    if fault == "relay":
        stage["services"]["mailpit"]["environment"]["MP_SMTP_RELAY_CONFIG"] = "/bad"
    assert validate(stage, stage["name"], environment="staging")


def test_cross_profile_collisions_and_reused_secret_material_are_rejected(
    profiles: tuple[dict[str, Any], dict[str, Any]], tmp_path: Path
) -> None:
    prod, stage = profiles
    original = copy.deepcopy(stage)
    stage["secrets"]["django_key"]["file"] = prod["secrets"]["django_key"]["file"]
    assert "secret_path_collision" in isolation_issues(prod, stage)
    stage = original
    for number, doc in enumerate((prod, stage)):
        for index, item in enumerate(doc["secrets"].values()):
            file = tmp_path / f"key-{number}-{index}"
            file.write_text((str(number) + str(index)) * 32)
            file.chmod(0o600)
            item["file"] = str(file)
    Path(stage["secrets"]["django_key"]["file"]).write_bytes(
        Path(prod["secrets"]["django_key"]["file"]).read_bytes()
    )
    assert "secret_material_reused" in isolation_issues(prod, stage, material=True)


def test_capacity_guard_is_closed_until_review_and_actual_headroom(
    profiles: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    _, stage = profiles
    good = {
        "available_memory_bytes": 4 * 1024**3,
        "free_disk_bytes": 5 * 1024**3,
        "load_per_core": 0.1,
        "limits_enforced": True,
    }
    issues, required = lifecycle.capacity_issues(stage, {}, good)
    assert issues == ["capacity_review_required"] and required == 1728 * 1024**2
    assert lifecycle.capacity_issues(stage, {"capacity_reviewed": True}, good)[0] == []
    unsupported = good | {"limits_enforced": False}
    assert lifecycle.capacity_issues(stage, {"capacity_reviewed": True}, unsupported)[0] == [
        "resource_limits_not_enforced"
    ]
    bad = {
        "available_memory_bytes": 1,
        "free_disk_bytes": 1,
        "load_per_core": 1.5,
        "limits_enforced": True,
    }
    assert set(lifecycle.capacity_issues(stage, {"capacity_reviewed": True}, bad)[0]) == {
        "insufficient_available_memory",
        "insufficient_disk",
        "insufficient_cpu_headroom",
    }


def test_stop_targets_only_staging_and_retains_volumes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(
        lifecycle, "compose", lambda _: ["docker", "compose", "--project-name", "muqola-staging"]
    )

    def record(command: list[str]) -> bytes:
        seen.append(command)
        return b""

    monkeypatch.setattr(lifecycle, "run", record)
    result = lifecycle.operate(
        {
            "project": "muqola-staging",
            "environment": "staging",
            "compose_file": "compose.staging.yaml",
        },
        "stop",
    )
    assert result["volumes_preserved"] and seen[0][4:] == [
        "stop",
        "--timeout",
        "30",
        "web",
        "worker",
        "mailpit",
        "db",
    ]
    assert not any("down" in value or "--volumes" in value for value in seen[0])
    with pytest.raises(OperationError):
        lifecycle.operate(
            {
                "project": "muqola-prod",
                "environment": "staging",
                "compose_file": "compose.staging.yaml",
            },
            "stop",
        )


@pytest.fixture
def deployed_staging(
    profiles: tuple[dict[str, Any], dict[str, Any]], tmp_path: Path
) -> dict[str, Any]:
    _, document = profiles
    root = tmp_path / "staging" / "cd"
    model = root / "models" / ("b" * 64) / "compose.json"
    image = "ghcr.io/tlamart/muqola@sha256:" + "b" * 64
    for name in ("web", "worker", "migrate"):
        document["services"][name]["image"] = image
    atomic_json(model, document)
    (root / "active").symlink_to(model.parent, target_is_directory=True)
    atomic_json(
        root / "state.json",
        {"phase": "succeeded", "current": {"image": image, "compose_file": str(model)}},
    )
    return {
        "project": "muqola-staging",
        "environment": "staging",
        "compose_file": "compose.staging.yaml",  # Source still references image a.
        "state_file": str(root.parent / "state.json"),
        "app_url": "https://staging.muqola.tlam.art",
    }


@pytest.mark.parametrize("action", ["start", "stop", "status"])
@pytest.mark.parametrize("explicit_active", [False, True])
def test_staging_lifecycle_keeps_cd_image_after_stop_start(
    deployed_staging: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    explicit_active: bool,
) -> None:
    config = deployed_staging
    root = Path(config["state_file"]).parent / "cd"
    model = (root / "active" / "compose.json").resolve()
    if explicit_active:
        config["compose_file"] = str(root / "active" / "compose.json")
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(lifecycle, "preflight", lambda _: {"issues": []})
    monkeypatch.setattr(lifecycle, "private_access_blocked", lambda _: True)
    monkeypatch.setattr(lifecycle, "protected_probe", lambda *args: True)
    monkeypatch.setattr(
        lifecycle, "compose", lambda c: ["docker", "compose", "-f", c["compose_file"]]
    )
    config["probe_credentials_file"] = "synthetic.json"
    seen: list[list[str]] = []

    def command(args: list[str]) -> bytes:
        seen.append(args)
        return b"[]" if "ps" in args else b""

    monkeypatch.setattr(lifecycle, "run", command)
    lifecycle.operate(config, action)
    assert seen and all(cmd[3] == str(model) for cmd in seen)
    assert {
        json.loads(model.read_text())["services"][name]["image"]
        for name in ("web", "worker", "migrate")
    } == {"ghcr.io/tlamart/muqola@sha256:" + "b" * 64}


@pytest.mark.parametrize(
    "fault",
    [
        "missing_model",
        "wrong_image",
        "wrong_project",
        "outside_root",
        "missing_state",
        "incomplete_release",
    ],
)
def test_invalid_active_staging_never_falls_back_to_old_image(
    deployed_staging: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    config = deployed_staging
    root = Path(config["state_file"]).parent / "cd"
    model = (root / "active" / "compose.json").resolve()
    document = json.loads(model.read_text())
    if fault == "missing_model":
        model.unlink()
    elif fault in {"wrong_image", "wrong_project"}:
        if fault == "wrong_image":
            document["services"]["web"]["image"] = "ghcr.io/tlamart/muqola@sha256:" + "a" * 64
        else:
            document["name"] = "muqola-prod"
        atomic_json(model, document)
    elif fault == "outside_root":
        (root / "active").unlink()
        outside = root.parent / "other"
        atomic_json(outside / "compose.json", document)
        (root / "active").symlink_to(outside, target_is_directory=True)
    elif fault == "missing_state":
        (root / "state.json").unlink()
    else:
        state = json.loads((root / "state.json").read_text())
        atomic_json(root / "state.json", state | {"phase": "failed"})
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(lifecycle, "preflight", lambda _: {"issues": []})
    monkeypatch.setattr(lifecycle, "compose", lambda _: ["synthetic"])
    calls: list[list[str]] = []
    monkeypatch.setattr(lifecycle, "run", lambda args: calls.append(args))
    with pytest.raises(OperationError):
        lifecycle.operate(config, "start")
    assert not calls


def test_start_refuses_public_access_before_starting_any_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(lifecycle, "compose", lambda _: ["synthetic-staging"])
    monkeypatch.setattr(lifecycle, "preflight", lambda _: {"issues": []})
    monkeypatch.setattr(lifecycle, "private_access_blocked", lambda _: False)
    commands: list[list[str]] = []
    monkeypatch.setattr(lifecycle, "run", lambda args: commands.append(args))
    with pytest.raises(OperationError, match="staging_access_not_private"):
        lifecycle.operate(
            {
                "project": "muqola-staging",
                "environment": "staging",
                "compose_file": "compose.staging.yaml",
                "app_url": "https://staging.muqola.tlam.art",
            },
            "start",
        )
    assert commands == []


def test_start_failure_never_applies_migrations_or_touches_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(lifecycle, "compose", lambda _: ["synthetic-staging"])
    monkeypatch.setattr(lifecycle, "preflight", lambda _: {"issues": []})
    monkeypatch.setattr(lifecycle, "private_access_blocked", lambda _: True)

    def command(args: list[str]) -> bytes:
        commands.append(args)
        if "--check" in args:
            raise OperationError("command_failed")
        return b""

    monkeypatch.setattr(lifecycle, "run", command)
    with pytest.raises(OperationError, match="pending_migrations_require_review"):
        lifecycle.operate(
            {
                "project": "muqola-staging",
                "environment": "staging",
                "compose_file": "compose.staging.yaml",
                "app_url": "https://staging.muqola.tlam.art",
            },
            "start",
        )
    assert len(commands) == 2 and "--check" in commands[-1]
    assert not any("--noinput" in cmd or "build" in cmd for cmd in commands)


@pytest.mark.django_db
@override_settings(DEPLOYMENT_ENV="staging")
def test_staging_requires_fictional_email_and_explicit_adult_attestation(client: Client) -> None:
    payload = {
        "email": "real@example.org",
        "display_name": "Test",
        "password": "Synthetic-test-password-2026!",
        "password_confirm": "Synthetic-test-password-2026!",
        "adult_confirmed": "on",
    }
    form = SignupForm(payload)
    assert not form.is_valid() and "email" in form.errors
    with pytest.raises(ValidationError):
        register(payload["email"], "Test", payload["password"], adult_confirmed=True)
    payload["email"] = "test@example.test"
    assert SignupForm(payload).is_valid()
    with pytest.raises(ValidationError):
        register(payload["email"], "Test", payload["password"])
    assert not User.objects.exists()


@pytest.mark.django_db
@override_settings(DEPLOYMENT_ENV="staging", APP_ENV="production")
def test_staging_cannot_satisfy_public_production_gate_and_keeps_legal_gate() -> None:
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("production_readiness", stdout=output)
    assert "production_deployment_required" in output.getvalue()
    output = StringIO()
    with pytest.raises(CommandError):
        call_command("staging_readiness", stdout=output)
    assert (
        "legal_review_required" in output.getvalue()
        and "runtime_database_privileges_too_broad" in output.getvalue()
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("EMAIL_HOST", "smtp.example.test"),
        ("EMAIL_HOST_USER", "provider-login"),
        ("EMAIL_HOST_PASSWORD", "synthetic-external-secret"),
        ("EMAIL_USE_TLS", "true"),
        ("POSTGRES_DB", "muqola"),
        ("POSTGRES_HOST", "production-db"),
        ("APP_ENV", "development"),
    ],
)
def test_runtime_refuses_unsafe_staging_before_connecting_to_any_database(
    key: str, value: str
) -> None:
    import os
    import sys

    environment = os.environ | {
        "APP_ENV": "production",
        "DEPLOYMENT_ENV": "staging",
        "APP_BASE_URL": "https://staging.muqola.tlam.art",
        "POSTGRES_DB": "muqola_staging",
        "POSTGRES_HOST": "db",
        "EMAIL_HOST": "mailpit",
        "EMAIL_PORT": "1025",
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
        "EMAIL_USE_TLS": "false",
        "EMAIL_USE_SSL": "false",
        key: value,
    }
    result = subprocess.run(  # noqa: S603 -- imports only, no DB connection
        [sys.executable, "-c", "import config.settings"],
        env=environment,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode != 0
    assert b"ImproperlyConfigured" in result.stderr
    assert b"synthetic-external-secret" not in result.stderr


def test_probe_origin_is_checked_before_production_reference_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(OperationError, match="staging_probe_origin"):
        lifecycle.preflight(
            {
                "project": "muqola-staging",
                "environment": "staging",
                "compose_file": "compose.staging.yaml",
                "app_url": "https://other.example.test",
            }
        )


def test_invalid_state_path_cannot_overwrite_another_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    state = tmp_path / "production" / "state.json"
    state.parent.mkdir()
    state.write_text("preserve-existing-synthetic-state")
    monkeypatch.setattr(lifecycle, "config_file", lambda _: {"state_file": str(state)})
    monkeypatch.setattr(sys, "argv", ["staging", "start", "--config", "synthetic.json"])
    assert lifecycle.main() == 1
    assert state.read_text() == "preserve-existing-synthetic-state"


@pytest.mark.parametrize("shared", [True, False])
def test_lifecycle_refuses_concurrent_cd_without_changing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shared: bool
) -> None:
    import sys

    root = tmp_path / "staging" / "cd"
    root.mkdir(parents=True)
    state = root.parent / "state.json"
    atomic_json(state, {"action": "stopped"})
    before = state.read_bytes()
    operator = tmp_path / "operator.json"
    atomic_json(operator, {"state_file": str(state)})
    lock_path = root.parent.parent / "cd.lock" if shared else root / "release.lock"
    calls: list[str] = []
    monkeypatch.setattr(lifecycle, "operate", lambda config, action: calls.append(action))
    monkeypatch.setattr(sys, "argv", ["staging", "start", "--config", str(operator)])
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert lifecycle.main() == 1
    assert not calls and state.read_bytes() == before


def test_capacity_measurement_refuses_remote_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "ssh://not-a-real-host")
    with pytest.raises(OperationError, match="local_docker_required"):
        lifecycle.host_resources(str(tmp_path))


def test_admission_checks_real_secret_values_before_any_start(
    profiles: tuple[dict[str, Any], dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prod, stage = profiles
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    for number, document in enumerate((prod, stage)):
        for index, value in enumerate(document["secrets"].values()):
            path = tmp_path / f"secret-{number}-{index}"
            path.write_text(f"synthetic-{number}-{index}-" * 8)
            path.chmod(0o600)
            value["file"] = str(path)
    reference = tmp_path / "production.json"
    reference.write_text(json.dumps({"project": "muqola-prod"}))
    reference.chmod(0o600)
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"username": "synthetic", "password": "synthetic-private"}))
    credentials.chmod(0o600)
    env = tmp_path / "staging.env"
    env.write_text("SYNTHETIC=true")
    env.chmod(0o600)
    config = {
        "environment": "staging",
        "project": "muqola-staging",
        "compose_file": "compose.staging.yaml",
        "compose_env": str(env),
        "app_url": "https://staging.muqola.tlam.art",
        "production_config": str(reference),
        "probe_credentials_file": str(credentials),
        "data_path": str(tmp_path),
        "synthetic_data_only": True,
        "capacity_reviewed": True,
    }
    monkeypatch.setattr(
        lifecycle, "rendered", lambda value: stage if value["project"] == "muqola-staging" else prod
    )
    monkeypatch.setattr(
        lifecycle,
        "host_resources",
        lambda _: {
            "available_memory_bytes": 4 * 1024**3,
            "free_disk_bytes": 8 * 1024**3,
            "load_per_core": 0.1,
            "limits_enforced": True,
        },
    )
    assert lifecycle.preflight(config)["issues"] == []
    Path(stage["secrets"]["django_key"]["file"]).write_bytes(
        Path(prod["secrets"]["django_key"]["file"]).read_bytes()
    )
    seen: list[list[str]] = []

    def record(command: list[str]) -> bytes:
        seen.append(command)
        return b""

    monkeypatch.setattr(lifecycle, "run", record)
    result = lifecycle.operate(config, "start")
    assert result["action"] == "start_refused" and "secret_material_reused" in result["issues"]
    assert seen == []


def test_host_resources_recognizes_docker_info_cpu_quota_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Docker's JSON field is CpuCfsQuota; an acronym-only spelling silently fails.
    docker_info = {
        "MemoryLimit": True,
        "CpuCfsQuota": True,
        "CgroupDriver": "systemd",
        "NCPU": 2,
    }
    monkeypatch.setattr(lifecycle, "require_local_docker", lambda: None)
    monkeypatch.setattr(lifecycle, "run", lambda _: json.dumps(docker_info).encode())
    assert lifecycle.host_resources(str(tmp_path))["limits_enforced"] is True
    docker_info["CpuCfsQuota"] = False
    assert lifecycle.host_resources(str(tmp_path))["limits_enforced"] is False
    docker_info["CpuCfsQuota"] = True
    docker_info["CgroupDriver"] = "none"
    assert lifecycle.host_resources(str(tmp_path))["limits_enforced"] is False


@pytest.mark.parametrize("explicit_context", [False, True])
def test_local_daemon_selection_preserves_docker_context_precedence(
    monkeypatch: pytest.MonkeyPatch, explicit_context: bool
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix://host.sock")
    if explicit_context:
        monkeypatch.setenv("DOCKER_CONTEXT", "selected")
    else:
        monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(lifecycle, "run", lambda _: b'"unix://context.sock"')
    assert lifecycle.require_local_docker() == (
        "unix://context.sock" if explicit_context else "unix://host.sock"
    )
