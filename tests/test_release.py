"""Release refusal, one-shot migration journal, rollback and trusted transport."""

import argparse
import copy
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.core.management import call_command

from deploy import delivery, release
from deploy.common import OperationError, atomic_json, utcnow


@pytest.mark.django_db(transaction=True)
def test_release_snapshot_is_read_only_and_stable() -> None:
    first, second = StringIO(), StringIO()
    call_command("release_snapshot", stdout=first)
    call_command("release_snapshot", stdout=second)
    assert json.loads(first.getvalue()) == json.loads(second.getvalue())
    snapshot = json.loads(first.getvalue())
    assert not snapshot["bootstrap"] and not snapshot["pending"] and not snapshot["invalid_indexes"]


def test_reviewed_policy_matches_only_committed_historical_migrations() -> None:
    import hashlib

    from muqola.operations.migration_policy import REVIEWED

    for path in Path("muqola").glob("*/migrations/[0-9]*.py"):
        assert (
            REVIEWED[f"{path.parts[1]}/{path.stem}"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )


@pytest.mark.parametrize("fault", ["bootstrap", "index", "unknown"])
def test_snapshot_refuses_bootstrap_invalid_index_or_unknown_migration(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    value: dict[str, Any] = {
        "bootstrap": False,
        "invalid_indexes": 0,
        "pending": [],
        "schema": "a" * 64,
    }
    if fault == "bootstrap":
        value["bootstrap"] = True
    elif fault == "index":
        value["invalid_indexes"] = 1
    else:
        value["pending"] = [{"reviewed": False}]
    monkeypatch.setattr(release, "run", lambda _: json.dumps(value).encode())
    with pytest.raises(OperationError):
        release.snapshot(["synthetic"])


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"current": {"image": "previous", "schema": "a" * 64}}
    plan = {
        "image": "candidate",
        "nonce": "f" * 32,
        "schema": "a" * 64,
        "pending": [{"migration": "reviewed"}],
        "compose_file": "synthetic.json",
        "commit": "b" * 40,
        "environment": "production",
    }
    key = release.digest(plan)
    atomic_json(
        tmp_path / "plans" / (key + ".json"), {"created_at": utcnow().isoformat(), "plan": plan}
    )
    monkeypatch.setattr(release, "make_plan", lambda *args: copy.deepcopy(plan))
    monkeypatch.setattr(release, "compose", lambda _: ["synthetic"])
    snapshots = iter([{"schema": "a" * 64, "pending": []}, {"schema": "c" * 64, "pending": []}])
    monkeypatch.setattr(release, "snapshot", lambda _: next(snapshots))
    monkeypatch.setattr(release, "https_ready", lambda _: None)
    commands: list[list[str]] = []

    def command(args: list[str]) -> bytes:
        commands.append(args)
        return b""

    monkeypatch.setattr(release, "run", command)
    return {
        "root": tmp_path,
        "state": state,
        "plan": plan,
        "key": key,
        "commands": commands,
        "config": {"environment": "production"},
        "payload": {"publication": {"image": "candidate"}},
    }


def apply(value: dict[str, Any]) -> dict[str, Any]:
    return release.apply(
        value["config"], value["payload"], value["root"], value["state"], value["key"]
    )


def test_successful_release_records_previous_and_preserves_volumes(
    application: dict[str, Any],
) -> None:
    result = apply(application)
    assert result["phase"] == "succeeded"
    commands = application["commands"]
    assert sum(cmd[-1] == "migrate" for cmd in commands) == 1
    assert not any("down" in cmd or "--volumes" in cmd or "build" in cmd for cmd in commands)
    state = json.loads((application["root"] / "state.json").read_text())
    assert state["previous"] == application["state"]["current"]
    assert state["current"]["schema"] == "c" * 64
    assert all("--no-deps" in cmd for cmd in commands if "up" in cmd)
    assert (application["root"] / "active").is_symlink()


@pytest.mark.parametrize("fault", ["hash", "expired", "stale", "consumed"])
def test_invalid_or_reused_approval_never_stops_services(
    application: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    value = application
    if fault == "hash":
        value["key"] = "x" * 64
    elif fault == "expired":
        atomic_json(
            value["root"] / "plans" / (value["key"] + ".json"),
            {"created_at": (utcnow() - timedelta(hours=2)).isoformat(), "plan": value["plan"]},
        )
    elif fault == "stale":
        monkeypatch.setattr(
            release, "make_plan", lambda *args: dict(value["plan"], schema="d" * 64)
        )
    else:
        atomic_json(value["root"] / "consumed" / value["key"], {})
    with pytest.raises(OperationError):
        apply(value)
    assert value["commands"] == []


@pytest.mark.parametrize("failure", ["stop", "migration", "readiness", "up", "https"])
def test_failures_preserve_previous_state_and_consume_attempt(
    application: dict[str, Any], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    value = application

    def command(args: list[str]) -> bytes:
        value["commands"].append(args)
        if (
            (failure == "stop" and "stop" in args)
            or (failure == "migration" and args[-1] == "migrate")
            or (failure == "readiness" and args[-1] == "production_readiness")
            or (failure == "up" and "up" in args)
        ):
            raise OperationError("synthetic_failure")
        return b""

    monkeypatch.setattr(release, "run", command)
    if failure == "https":
        monkeypatch.setattr(
            release,
            "https_ready",
            lambda _: (_ for _ in ()).throw(OperationError("synthetic_https")),
        )
    with pytest.raises(OperationError):
        apply(value)
    saved = json.loads((value["root"] / "state.json").read_text())
    assert saved["phase"] == "failed" and saved["current"] == value["state"]["current"]
    assert (value["root"] / "history" / (value["key"] + ".json")).exists()
    assert (value["root"] / "consumed" / value["key"]).exists()
    if failure == "migration":
        assert saved["migration"] == "unknown"
    assert not any("restore" in arg or "down" == arg for cmd in value["commands"] for arg in cmd)


@pytest.mark.parametrize(
    "fault",
    [
        "backup_missing",
        "backup_failed",
        "backup_old",
        "restore_failed",
        "restore_old",
        "restore_wrong_env",
    ],
)
def test_backup_and_restore_gates_are_closed(tmp_path: Path, fault: str) -> None:
    config = {
        "project": "muqola-prod",
        "backup_status_file": str(tmp_path / "backup"),
        "restore_evidence_file": str(tmp_path / "restore"),
    }
    backup = {"ok": True, "object": "synthetic.dump.age", "last_success": utcnow().isoformat()}
    exercise = {
        "success": True,
        "isolated": True,
        "project": "muqola-prod",
        "reviewed_by": "synthetic operator",
        "exercise_id": "synthetic",
        "completed_at": utcnow().isoformat(),
    }
    if fault == "backup_failed":
        backup["ok"] = False
    if fault == "backup_old":
        backup["last_success"] = (utcnow() - timedelta(days=2)).isoformat()
    if fault == "restore_failed":
        exercise["success"] = False
    if fault == "restore_old":
        exercise["completed_at"] = (utcnow() - timedelta(days=31)).isoformat()
    if fault == "restore_wrong_env":
        exercise["project"] = "muqola-staging"
    if fault != "backup_missing":
        atomic_json(tmp_path / "backup", backup)
    atomic_json(tmp_path / "restore", exercise)
    with pytest.raises((OSError, OperationError)):
        release.prerequisites(config)


def test_delivery_workflow_is_manual_main_only_and_read_only() -> None:
    doc = yaml.load(Path(".github/workflows/deploy.yml").read_text(), Loader=yaml.BaseLoader)  # noqa: S506 -- strings only
    assert set(doc["on"]) == {"workflow_dispatch"}
    job = doc["jobs"]["delivery"]
    assert "refs/heads/main" in job["if"] and "tlamart/muqola" in job["if"]
    assert job["permissions"] == {"contents": "read", "actions": "read", "packages": "read"}
    assert doc["concurrency"]["cancel-in-progress"] == "false"
    assert job["environment"] == "${{ inputs.environment }}"
    assert not any("${{ inputs." in s.get("run", "") for s in job["steps"])
    assert "ssh-keyscan" not in Path("deploy/delivery.py").read_text()


@pytest.mark.parametrize(
    "host,user",
    [("bad;host", "deploy"), ("-flag", "deploy"), ("host", "root"), ("host", "bad user")],
)
def test_ssh_injection_rejected_before_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str, user: str
) -> None:
    monkeypatch.setenv("VPS_HOST", host)
    monkeypatch.setenv("VPS_USER", user)
    commands: list[Any] = []
    monkeypatch.setattr(delivery, "run", lambda args: commands.append(args))
    with pytest.raises(OperationError):
        delivery.ssh_options(tmp_path)
    assert not commands


def test_unknown_host_key_fails_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in {
        "VPS_HOST": "host.example.test",
        "VPS_USER": "deploy",
        "VPS_SSH_KEY": "synthetic-not-real",
        "SSH_KNOWN_HOSTS": "",
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(OperationError):
        delivery.ssh_options(tmp_path)


def test_non_main_dispatch_never_contacts_vps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    with pytest.raises(OperationError):
        delivery.deliver(argparse.Namespace())


@pytest.fixture
def planning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config = {
        "environment": "production",
        "project": "muqola-prod",
        "data_path": str(tmp_path),
        "compose_file": "synthetic.json",
    }
    publication = {"image": "candidate", "commit": "a" * 40}
    payload = {"publication": publication, "assets": {}, "kind": "deploy"}
    key = tmp_path / "key"
    key.write_text("synthetic-key")
    document = {"secrets": {"key": {"file": str(key)}}}
    monkeypatch.setattr(release, "prerequisites", lambda _: {"backup": "a", "restore": "b"})
    monkeypatch.setattr(release, "configuration", lambda *args: (config, document))
    monkeypatch.setattr(release, "capacity_issues", lambda *args: ([], 0))
    monkeypatch.setattr(release, "host_resources", lambda _: {})
    monkeypatch.setattr(release, "compose", lambda _: ["synthetic"])
    monkeypatch.setattr(release, "run", lambda _: b"")
    schema = {"schema": "b" * 64, "pending": []}
    monkeypatch.setattr(release, "snapshot", lambda _: schema)
    return {"config": config, "payload": payload, "root": tmp_path, "schema": schema}


@pytest.mark.parametrize("fault", ["no_previous", "different_image", "different_schema", "pending"])
def test_rollback_refuses_unproven_compatibility(planning: dict[str, Any], fault: str) -> None:
    value = planning
    value["payload"]["kind"] = "rollback"
    state: dict[str, Any] = {"previous": {"image": "candidate", "schema": "b" * 64}}
    if fault == "no_previous":
        state = {}
    elif fault == "different_image":
        state["previous"]["image"] = "other"
    elif fault == "different_schema":
        state["previous"]["schema"] = "c" * 64
    else:
        value["schema"]["pending"] = [{"migration": "safe"}]
    with pytest.raises(OperationError):
        release.make_plan(value["config"], value["payload"], value["root"], state)


def test_compatible_rollback_has_no_migration(planning: dict[str, Any]) -> None:
    value = planning
    value["payload"]["kind"] = "rollback"
    state: dict[str, Any] = {"previous": {"image": "candidate", "schema": "b" * 64}}
    plan = release.make_plan(value["config"], value["payload"], value["root"], state)
    assert plan["kind"] == "rollback" and not plan["pending"]


def test_unknown_migration_outcome_requires_manual_repair(planning: dict[str, Any]) -> None:
    value = planning
    value["schema"]["pending"] = [{"migration": "safe"}]
    with pytest.raises(OperationError, match="migration_outcome_requires_operator_review"):
        release.make_plan(
            value["config"], value["payload"], value["root"], {"migration": "unknown"}
        )


@pytest.mark.parametrize("global_lock", [False, True])
def test_host_lock_refuses_another_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, global_lock: bool
) -> None:
    import fcntl

    config_path = tmp_path / "config"
    atomic_json(config_path, {"environment": "production", "project": "muqola-prod"})
    root = tmp_path / "production" / "cd"
    root.mkdir(parents=True)
    monkeypatch.setattr(release, "locations", lambda _: (config_path, root))
    monkeypatch.setattr(release, "require_local_docker", lambda: None)
    with (tmp_path / "cd.lock" if global_lock else root / "release.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OperationError, match="release_in_progress"):
            release.operate("production", "plan", {"protocol": 1})


def test_schema_changed_after_stop_never_runs_migration(
    application: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "snapshot", lambda _: {"schema": "changed", "pending": []})
    with pytest.raises(OperationError, match="schema_changed_after_stop"):
        apply(application)
    assert len(application["commands"]) == 1 and "stop" in application["commands"][0]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_positive_transport_uses_explicit_assets_and_strict_ssh_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    for key, value in {
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "tlamart/muqola",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_ACTOR": "synthetic",
        "VPS_HOST": "host.example.test",
        "VPS_USER": "deploy",
        "VPS_SSH_KEY": "synthetic-key-not-for-use",
        "SSH_KNOWN_HOSTS": "host.example.test ssh-ed25519 synthetic",
        "GH_TOKEN": "synthetic-read-token",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    publication = {"commit": "a" * 40, "image": "candidate"}
    monkeypatch.setattr(delivery, "verify", lambda *args: publication)
    plan = {"environment": environment, "image": "candidate", "kind": "deploy"}
    result = {"hash": release.digest(plan), "plan": plan}
    commands: list[list[str]] = []
    requests: list[dict[str, Any]] = []

    def transport(args: list[str], **kwargs: Any) -> bytes:
        commands.append(args)
        if args[0] == "gh":
            import base64

            name = args[-1].split("/contents/", 1)[1].split("?", 1)[0]
            content = b"synthetic versioned asset"
            return json.dumps(
                {
                    "type": "file",
                    "path": name,
                    "size": len(content),
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode(),
                }
            ).encode()
        if args[0] == "ssh" and args[-1].startswith("cd "):
            requests.append(json.loads(kwargs["stdin"].read()))
            return json.dumps(result).encode()
        if args[0] == "scp":
            local = Path(args[-2])
            expected_mode = 0o755 if local.suffix == ".sh" else 0o644
            assert local.stat().st_mode & 0o777 == expected_mode
            assert "-p" in args
        return b""

    monkeypatch.setattr(delivery, "run", transport)
    monkeypatch.setattr(
        delivery, "remote_request", lambda args, stdin: json.loads(transport(args, stdin=stdin))
    )
    args = argparse.Namespace(
        environment=environment,
        action="plan",
        kind="deploy",
        image="candidate",
        publication_run=123,
        publication_attempt=1,
    )
    assert delivery.deliver(args) == result
    assert len([cmd for cmd in commands if cmd[0] == "scp"]) == len(release.ASSETS)
    assert requests[0]["protocol"] == 1 and set(requests[0]["assets"]) == set(release.ASSETS)
    for cmd in commands:
        assert "synthetic-read-token" not in str(cmd)
        if cmd[0] in {"ssh", "scp"}:
            assert "StrictHostKeyChecking=yes" in cmd and "ForwardAgent=no" in cmd
    assert (tmp_path / "work" / "plan.json").is_file()


@pytest.mark.django_db
def test_schema_fingerprint_detects_column_precision_change() -> None:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE release_schema_probe (value varchar(50))")
    first = StringIO()
    call_command("release_snapshot", stdout=first)
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE release_schema_probe ALTER COLUMN value TYPE varchar(100)")
    second = StringIO()
    call_command("release_snapshot", stdout=second)
    assert json.loads(first.getvalue())["schema"] != json.loads(second.getvalue())["schema"]
    # pytest's transaction rollback removes only this synthetic table.


@pytest.mark.parametrize("fault", ["none", "volume", "origin", "reused_secret"])
def test_real_compose_render_and_isolation_guards(tmp_path: Path, fault: str) -> None:
    import hashlib
    import shutil

    root = Path(__file__).resolve().parents[1]
    commit = "a" * 40
    incoming = tmp_path / "incoming" / commit
    for name in release.ASSETS:
        target = incoming / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    environments = {}
    for kind in ("production", "staging"):
        secrets = tmp_path / kind / "secrets"
        secrets.mkdir(parents=True, mode=0o700)
        for key in (
            "django_key",
            "db_admin_password",
            "db_app_password",
            "db_migrate_password",
            "smtp_password",
        ):
            path = secrets / key
            path.write_text((kind + "-" + key) * 8)
            path.chmod(0o600)
        text = (
            root / (".env.production.example" if kind == "production" else ".env.staging.example")
        ).read_text()
        text = text.replace("REPLACE_WITH_64_HEX_DIGEST", "b" * 64).replace(
            "REPLACE_WITH_CADDY_CONTAINER_IP", "192.0.2.10"
        )
        text = text.replace("/etc/muqola/staging/secrets", str(secrets)).replace(
            "/etc/muqola/secrets", str(secrets)
        )
        text = text.replace("/etc/muqola/staging/legal", str(tmp_path / kind / "legal")).replace(
            "/etc/muqola/legal", str(tmp_path / kind / "legal")
        )
        env = tmp_path / (kind + ".env")
        env.write_text(text)
        env.chmod(0o600)
        environments[kind] = env
    other = tmp_path / "stage-config"
    atomic_json(
        other,
        {
            "environment": "staging",
            "project": "muqola-staging",
            "compose_env": str(environments["staging"]),
            "compose_file": str(incoming / "compose.staging.yaml"),
        },
    )
    config = {
        "environment": "production",
        "project": "muqola-prod",
        "compose_env": str(environments["production"]),
        "staging_config": str(other),
    }
    if fault == "volume":
        path = incoming / "compose.prod.yaml"
        path.write_text(
            path.read_text().replace(
                "  postgres_data:\n", "  postgres_data:\n    name: unintended_data\n"
            )
        )
    if fault == "origin":
        path = environments["production"]
        path.write_text(path.read_text().replace("muqola.tlam.art", "other.example.test"))
    if fault == "reused_secret":
        (tmp_path / "staging" / "secrets" / "django_key").write_bytes(
            (tmp_path / "production" / "secrets" / "django_key").read_bytes()
        )
    publication = {
        "schema": 1,
        "repository": "tlamart/muqola",
        "workflow": ".github/workflows/ci.yml",
        "event": "push",
        "ref": "refs/heads/main",
        "commit": commit,
        "image": "ghcr.io/tlamart/muqola@sha256:" + "b" * 64,
        "run_id": 123,
        "run_attempt": 1,
        "candidate_artifact_id": 42,
        "image_id": "sha256:" + "c" * 64,
        "config_digest": "sha256:" + "d" * 64,
        "archive_sha256": "sha256:" + "e" * 64,
        "platform": "linux/amd64",
    }
    payload = {
        "publication": publication,
        "assets": {
            name: hashlib.sha256((incoming / name).read_bytes()).hexdigest()
            for name in release.ASSETS
        },
    }
    if fault != "none":
        with pytest.raises(OperationError):
            release.configuration(config, payload, tmp_path)
    else:
        runtime, model = release.configuration(config, payload, tmp_path)
        assert model["services"]["web"]["image"] == publication["image"]
        model_file = Path(runtime["compose_file"])
        assert model_file.stat().st_mode & 0o077 == 0
        original = model_file.read_bytes()
        import re

        env = environments["production"]
        env.write_text(
            re.sub(r"(?m)^EMAIL_FROM=.*$", "EMAIL_FROM=changed@example.test", env.read_text())
        )
        changed, _ = release.configuration(config, payload, tmp_path)
        assert changed["compose_file"] != runtime["compose_file"]
        assert model_file.read_bytes() == original  # a plan cannot overwrite the active model


def test_public_staging_is_refused_before_pull(
    planning: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    value = planning
    value["config"]["environment"] = "staging"
    monkeypatch.setattr(release, "preflight", lambda _: {"issues": []})
    monkeypatch.setattr(release, "private_access_blocked", lambda _: False)
    with pytest.raises(OperationError, match="staging_access_not_private"):
        release.make_plan(value["config"], value["payload"], value["root"], {})


@pytest.mark.parametrize(
    "issue", ["recent_successful_backup_required", "controller_protocol_mismatch"]
)
def test_remote_refusals_are_reported_without_raw_ssh_logs(
    monkeypatch: pytest.MonkeyPatch, issue: str
) -> None:
    from types import SimpleNamespace

    result = SimpleNamespace(
        returncode=1,
        stdout=json.dumps({"issues": [issue]}).encode(),
        stderr=b"synthetic-private-value",
    )
    monkeypatch.setattr("deploy.delivery.subprocess.run", lambda *args, **kwargs: result)
    with pytest.raises(OperationError, match="host_" + issue):
        delivery.remote_request(["synthetic"], None)


def test_transport_interruption_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    calls = []

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        raise subprocess.TimeoutExpired("synthetic", 1)

    monkeypatch.setattr("deploy.delivery.subprocess.run", interrupted)
    with pytest.raises(OperationError, match="inspect_state_before_replanning"):
        delivery.remote_request(["synthetic"], None)
    assert len(calls) == 1


def test_identical_replanned_state_has_a_new_approval_and_restores_auth_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    root = tmp_path / "production" / "cd"
    path = tmp_path / "operator.json"
    atomic_json(path, {"environment": "production", "project": "muqola-prod"})
    monkeypatch.setattr(release, "locations", lambda _: (path, root))
    monkeypatch.setattr(release, "require_local_docker", lambda: None)
    monkeypatch.setattr(
        release, "make_plan", lambda *args: {"schema": "a" * 64, "image": "candidate"}
    )
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: b"")
    monkeypatch.setenv("DOCKER_CONFIG", "original-context")
    payload = {"protocol": 1, "registry_token": "synthetic-token", "registry_user": "synthetic"}
    first = release.operate("production", "plan", dict(payload))
    second = release.operate("production", "plan", dict(payload))
    assert first["hash"] != second["hash"]
    assert os.environ["DOCKER_CONFIG"] == "original-context"


@pytest.fixture
def plan_evidence(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import io
    import zipfile

    plan = {"environment": "production", "image": "candidate", "kind": "deploy"}
    value = {"hash": release.digest(plan), "plan": plan}
    source = {
        "id": 123,
        "repository": {"full_name": "tlamart/muqola"},
        "event": "workflow_dispatch",
        "head_branch": "main",
        "path": ".github/workflows/deploy.yml",
        "status": "completed",
        "conclusion": "success",
        "head_repository": {"full_name": "tlamart/muqola"},
        "run_attempt": 1,
    }
    artifact = {
        "id": 456,
        "name": "muqola-plan-production-1",
        "expired": False,
        "size_in_bytes": 1024,
        "workflow_run": {"id": 123},
    }
    fixture: dict[str, Any] = {
        "source": source,
        "artifact": artifact,
        "value": value,
        "filename": "plan.json",
    }
    monkeypatch.setattr(
        "deploy.delivery.GitHubEvidence.get",
        lambda self, path: (
            {"total_count": 1, "artifacts": [artifact]} if "artifacts?" in path else source
        ),
    )

    def archive(args: list[str]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as contents:
            contents.writestr(fixture["filename"], json.dumps(value))
        return output.getvalue()

    monkeypatch.setattr(delivery, "run", archive)
    return fixture


def test_plan_source_is_read_from_latest_successful_dispatch_artifact(
    plan_evidence: dict[str, Any],
) -> None:
    value = plan_evidence["value"]
    assert delivery.approved_plan("production", 123, value["hash"]) == value


@pytest.mark.parametrize(
    "fault",
    [
        "event",
        "branch",
        "workflow",
        "failure",
        "foreign_repo",
        "expired",
        "old_attempt",
        "filename",
        "hash",
        "environment",
    ],
)
def test_untrusted_plan_artifacts_are_refused(plan_evidence: dict[str, Any], fault: str) -> None:
    value = plan_evidence
    expected = value["value"]["hash"]
    if fault == "event":
        value["source"]["event"] = "pull_request"
    elif fault == "branch":
        value["source"]["head_branch"] = "feature"
    elif fault == "workflow":
        value["source"]["path"] = ".github/workflows/ci.yml"
    elif fault == "failure":
        value["source"]["conclusion"] = "failure"
    elif fault == "foreign_repo":
        value["source"]["head_repository"]["full_name"] = "other/repo"
    elif fault == "expired":
        value["artifact"]["expired"] = True
    elif fault == "old_attempt":
        value["source"]["run_attempt"] = 2
    elif fault == "filename":
        value["filename"] = "../plan.json"
    elif fault == "hash":
        value["value"]["hash"] = "f" * 64
    else:
        value["value"]["plan"]["environment"] = "staging"
    with pytest.raises(OperationError):
        delivery.approved_plan("production", 123, expected)


def test_still_running_migration_prevents_any_new_plan(
    planning: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def active(args: list[str]) -> bytes:
        commands.append(args)
        return b"synthetic-migration-container"

    monkeypatch.setattr(release, "run", active)
    value = planning
    with pytest.raises(OperationError, match="migration_container_still_running"):
        release.make_plan(value["config"], value["payload"], value["root"], {})
    assert len(commands) == 1 and commands[0][:2] == ["docker", "ps"]


def test_registry_auth_pins_the_verified_local_daemon_and_restores_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    root = tmp_path / "production" / "cd"
    path = tmp_path / "operator.json"
    atomic_json(path, {"environment": "production", "project": "muqola-prod"})
    monkeypatch.setattr(release, "locations", lambda _: (path, root))
    monkeypatch.setattr(release, "require_local_docker", lambda: "unix://selected.sock")
    monkeypatch.setattr(release, "make_plan", lambda *args: {"schema": "a" * 64})

    def login(*args: Any, **kwargs: Any) -> bytes:
        assert os.environ["DOCKER_HOST"] == "unix://selected.sock"
        assert "DOCKER_CONTEXT" not in os.environ
        return b""

    monkeypatch.setattr(release, "run", login)
    monkeypatch.setenv("DOCKER_HOST", "unix://original.sock")
    monkeypatch.setenv("DOCKER_CONTEXT", "original-name")
    release.operate(
        "production",
        "plan",
        {"protocol": 1, "registry_token": "synthetic", "registry_user": "synthetic"},
    )
    assert os.environ["DOCKER_HOST"] == "unix://original.sock"
    assert os.environ["DOCKER_CONTEXT"] == "original-name"


@pytest.mark.parametrize(
    "phase,accepted", [("succeeded", False), ("failed", True), ("applying", True)]
)
def test_live_candidate_is_recoverable_only_after_a_recorded_attempt(
    planning: dict[str, Any], monkeypatch: pytest.MonkeyPatch, phase: str, accepted: bool
) -> None:
    value = planning

    def live(args: list[str]) -> bytes:
        if args[:2] == ["docker", "ps"]:
            return b""
        if "ps" in args:
            return b"synthetic-container"
        if args[:2] == ["docker", "inspect"]:
            return b'[{"Config":{"Image":"candidate"}}]'
        return b""

    monkeypatch.setattr(release, "run", live)
    state: dict[str, Any] = {"phase": phase, "candidate": "candidate"}
    if accepted:
        plan = release.make_plan(value["config"], value["payload"], value["root"], state)
        assert plan["running_images"] == ["candidate"] and plan["previous"] is None
    else:
        with pytest.raises(OperationError, match="reviewed_adoption"):
            release.make_plan(value["config"], value["payload"], value["root"], state)


@pytest.mark.parametrize("phase", ["failed", "applying"])
def test_rollback_after_failed_candidate_targets_last_successful_current(
    planning: dict[str, Any], phase: str
) -> None:
    value = planning
    value["payload"]["kind"] = "rollback"
    state: dict[str, Any] = {
        "phase": phase,
        "current": {"image": "candidate", "schema": "b" * 64},
        "previous": {"image": "older", "schema": "b" * 64},
        "candidate": "failed-image",
    }
    plan = release.make_plan(value["config"], value["payload"], value["root"], state)
    assert plan["image"] == state["current"]["image"]
