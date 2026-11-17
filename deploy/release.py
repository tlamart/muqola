"""Host release controller. Private configuration, plan hash, lock and one-shot application.

No builds, destructive migrations, database restores or volume removals.
Installed independently by the operator; SSH receives only reviewed release assets.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import ssl
import tempfile
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import HTTPSHandler, ProxyHandler, build_opener

from deploy.check_config import validate
from deploy.common import OperationError, atomic_json, compose, config_file, run, utcnow
from deploy.image_provenance import SHA, validate_record
from deploy.probe import NoRedirect, private_access_blocked, protected_probe
from deploy.staging import capacity_issues, host_resources, preflight, require_local_docker
from deploy.staging_config import isolation_issues

ASSETS = (
    "compose.prod.yaml",
    "compose.staging.yaml",
    "compose.runtime.yaml",
    "deploy/migrate.sh",
    "deploy/postgres/10-roles.sh",
    "deploy/postgres/dump.sh",
    "deploy/postgres/restore.sh",
    "deploy/postgres/runtime-grants.sql",
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def recent(stamp: str, hours: int) -> bool:
    return timedelta(0) <= utcnow() - datetime.fromisoformat(stamp) <= timedelta(hours=hours)


def prerequisites(config: dict[str, Any]) -> dict[str, str]:
    backup = config_file(Path(config["backup_status_file"]))
    exercise = config_file(Path(config["restore_evidence_file"]))
    if not backup.get("ok") or not backup.get("object") or not recent(backup["last_success"], 24):
        raise OperationError("recent_successful_backup_required")
    if (
        exercise.get("success") is not True
        or exercise.get("isolated") is not True
        or exercise.get("project") != config["project"]
        or not exercise.get("reviewed_by")
        or not exercise.get("exercise_id")
        or not recent(exercise["completed_at"], 24 * 30)
    ):
        raise OperationError("reviewed_isolated_restore_required")
    return {"backup": digest(backup), "restore": digest(exercise)}


def snapshot(command: list[str]) -> dict[str, Any]:
    value = json.loads(
        run(
            [
                *command,
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                "python",
                "manage.py",
                "release_snapshot",
            ]
        )
    )
    if value["bootstrap"]:
        raise OperationError("bootstrap_requires_separate_reviewed_initialization")
    if value["invalid_indexes"] or any(not item["reviewed"] for item in value["pending"]):
        raise OperationError("unknown_or_unhealthy_migrations")
    return value  # type: ignore[no-any-return]


def assets(directory: Path, expected: dict[str, str]) -> None:
    if set(expected) != set(ASSETS):
        raise OperationError("explicit_asset_manifest_required")
    for name in ASSETS:
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]
        ):
            raise OperationError("release_assets_mismatch")


def configuration(
    config: dict[str, Any], payload: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = payload["publication"]
    validate_record(record, record["image"], record["run_id"], record["run_attempt"])
    commit = record["commit"]
    if not SHA.fullmatch(commit):
        raise OperationError("invalid_commit")
    source = root / "incoming" / commit
    assets(source, payload["assets"])
    runtime = dict(
        config,
        compose_file=str(
            source
            / (
                "compose.staging.yaml"
                if config["environment"] == "staging"
                else "compose.prod.yaml"
            )
        ),
    )
    # Resolve private env and bind paths without printing the rendered document.
    document = json.loads(run([*compose(runtime), "--profile", "*", "config", "--format", "json"]))
    for service in ("web", "worker", "migrate"):
        document["services"][service]["image"] = record["image"]
    issues = validate(document, config["project"], environment=config["environment"])
    domain = "staging.muqola.tlam.art" if config["environment"] == "staging" else "muqola.tlam.art"
    for name in ("web", "worker", "migrate"):
        settings = document["services"][name]["environment"]
        if (
            settings.get("APP_BASE_URL") != "https://" + domain
            or settings.get("ALLOWED_HOSTS") != domain
            or settings.get("DEPLOYMENT_ENV") != config["environment"]
        ):
            issues.append("origin_or_environment_mismatch")
    volume = document["volumes"].get("postgres_data", {})
    if volume.get("name") != config["project"] + "_postgres_data" or volume.get("external"):
        issues.append("persistent_volume_identity_mismatch")
    mounts = [
        v
        for v in document["services"]["db"].get("volumes", [])
        if v.get("target") == "/var/lib/postgresql/data"
    ]
    if (
        len(mounts) != 1
        or mounts[0].get("source") != "postgres_data"
        or mounts[0].get("type") != "volume"
    ):
        issues.append("database_volume_mount_mismatch")
    if issues:
        raise OperationError("release_compose_preflight_failed")
    if config["environment"] == "production":
        other = config_file(Path(config["staging_config"]))
        other_model = json.loads(
            run([*compose(other), "--profile", "*", "config", "--format", "json"])
        )
        if validate(other_model, "muqola-staging", environment="staging") or isolation_issues(
            document, other_model, material=True
        ):
            raise OperationError("production_staging_isolation_required")
    target = root / "models" / digest([record["image"], payload["assets"], document])
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(target / "compose.json", document)
    runtime["compose_file"] = str(target / "compose.json")
    return runtime, document


def make_plan(
    config: dict[str, Any], payload: dict[str, Any], root: Path, state: dict[str, Any]
) -> dict[str, Any]:
    evidence = prerequisites(config)
    active = run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=" + config["project"],
            "--filter",
            "label=com.docker.compose.service=migrate",
            "--format",
            "{{.ID}}",
        ]
    )
    if active.strip():
        raise OperationError("migration_container_still_running")
    runtime, document = configuration(config, payload, root)
    if config["environment"] == "staging":
        stage_config = dict(
            runtime,
            compose_file=str(
                root / "incoming" / payload["publication"]["commit"] / "compose.staging.yaml"
            ),
        )
        stage = preflight(stage_config)
        if stage["issues"]:
            raise OperationError("staging_admission_failed")
        if not private_access_blocked("https://staging.muqola.tlam.art/health/ready/"):
            raise OperationError("staging_access_not_private")
    else:
        issues, _ = capacity_issues(document, config, host_resources(config["data_path"]))
        if issues:
            raise OperationError("production_capacity_review_required")
    command = compose(runtime)
    run([*command, "pull", "web", "worker", "migrate"])
    schema = snapshot(command)
    containers = run([*command, "ps", "-q", "web", "worker"]).decode().split()
    observed = (
        sorted(
            {
                item["Config"]["Image"]
                for item in json.loads(run(["docker", "inspect", *containers]))
            }
        )
        if containers
        else []
    )
    known = {state["current"]["image"]} if state.get("current") else set()
    if state.get("phase") in {"failed", "applying"} and state.get("candidate"):
        known.add(state["candidate"])
    if observed and not set(observed) <= known:
        raise OperationError("live_deployment_requires_reviewed_adoption")
    if state.get("migration") == "unknown" and schema["pending"]:
        raise OperationError("migration_outcome_requires_operator_review")
    kind = payload["kind"]
    if kind not in {"deploy", "rollback"}:
        raise OperationError("invalid_release_kind")
    previous = state.get("current")
    if kind == "rollback":
        rollback = (
            state.get("current")
            if state.get("phase") in {"failed", "applying"}
            else state.get("previous")
        )
        if (
            not rollback
            or rollback["image"] != payload["publication"]["image"]
            or rollback["schema"] != schema["schema"]
            or schema["pending"]
        ):
            raise OperationError("rollback_schema_or_image_incompatible")
    # Bind configuration and secret file contents without disclosing paths/values.
    secret_hashes = [
        hashlib.sha256(Path(value["file"]).read_bytes()).hexdigest()
        for value in document["secrets"].values()
    ]
    return {
        "environment": config["environment"],
        "kind": kind,
        "image": payload["publication"]["image"],
        "commit": payload["publication"]["commit"],
        "publication": digest(payload["publication"]),
        "assets": payload["assets"],
        "schema": schema["schema"],
        "pending": schema["pending"],
        "previous": previous,
        "running_images": observed,
        "state": digest(state),
        "evidence": evidence,
        "configuration": digest([config, document, secret_hashes]),
        "compose_file": runtime["compose_file"],
    }


def https_ready(config: dict[str, Any]) -> None:
    url = (
        "https://staging.muqola.tlam.art"
        if config["environment"] == "staging"
        else "https://muqola.tlam.art"
    ) + "/health/ready/"
    if config["environment"] == "staging":
        ok = protected_probe(url, Path(config["probe_credentials_file"]))
    else:
        opener = build_opener(
            ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect()
        )
        with opener.open(url, timeout=10) as response:  # noqa: S310 -- literal HTTPS origin
            ok = response.status == 200
    if not ok:
        raise OperationError("release_https_failed")


def apply(
    config: dict[str, Any],
    payload: dict[str, Any],
    root: Path,
    state: dict[str, Any],
    approved: str,
) -> dict[str, Any]:
    if not SHA256.fullmatch(approved):
        raise OperationError("approved_plan_hash_required")
    saved = config_file(root / "plans" / (approved + ".json"))
    if digest(saved["plan"]) != approved or not recent(saved["created_at"], 1):
        raise OperationError("approved_plan_expired_or_modified")
    expected = dict(saved["plan"])
    nonce = expected.pop("nonce", "")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise OperationError("unique_reviewed_plan_required")
    plan = dict(make_plan(config, payload, root, state))
    plan.pop("nonce", None)
    if plan != expected:
        raise OperationError("plan_stale_replan_required")
    if not recent(saved["created_at"], 1):
        raise OperationError("approved_plan_expired_or_modified")
    journal = root / "state.json"
    if (root / "consumed" / approved).exists():
        raise OperationError("plan_already_consumed")
    atomic_json(root / "consumed" / approved, {"at": utcnow().isoformat()})
    progress = dict(
        state,
        phase="applying",
        plan=approved,
        candidate=plan["image"],
        migration="not_started",
        started_at=utcnow().isoformat(),
    )
    atomic_json(journal, progress)
    runtime = dict(config, compose_file=plan["compose_file"])
    command = compose(runtime)
    try:
        run([*command, "stop", "--timeout", "30", "web", "worker"])
        if snapshot(command)["schema"] != plan["schema"]:
            raise OperationError("schema_changed_after_stop")
        if plan["pending"]:
            progress["migration"] = "unknown"
            atomic_json(journal, progress)
            run([*command, "run", "--rm", "--no-deps", "migrate"])
        progress["migration"] = "succeeded"
        atomic_json(journal, progress)
        after = snapshot(command)
        if after["pending"]:
            raise OperationError("migrations_incomplete")
        readiness = (
            "staging_readiness" if config["environment"] == "staging" else "production_readiness"
        )
        run([*command, "run", "--rm", "--no-deps", "web", "python", "manage.py", readiness])
        run(
            [
                *command,
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--wait",
                "--wait-timeout",
                "120",
                "web",
                "worker",
            ]
        )
        https_ready(config)
        current = {
            "image": plan["image"],
            "schema": after["schema"],
            "commit": plan["commit"],
            "compose_file": plan["compose_file"],
            "publication": payload["publication"],
        }
        success = dict(
            progress,
            phase="succeeded",
            current=current,
            previous=state.get("current"),
            completed_at=utcnow().isoformat(),
        )
        link = root / ".active-next"
        link.unlink(missing_ok=True)
        link.symlink_to(Path(plan["compose_file"]).parent, target_is_directory=True)
        os.replace(link, root / "active")
        atomic_json(root / "history" / (approved + ".json"), success)
        atomic_json(journal, success)
        return {"phase": "succeeded", "image": plan["image"], "schema": after["schema"]}
    except Exception:
        failure = dict(progress, phase="failed", completed_at=utcnow().isoformat())
        atomic_json(root / "history" / (approved + ".json"), failure)
        atomic_json(journal, failure)
        raise


SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def locations(environment: str) -> tuple[Path, Path]:
    return (
        Path(
            "/etc/muqola/staging/release.json"
            if environment == "staging"
            else "/etc/muqola/release.json"
        ),
        Path(f"/var/lib/muqola/{environment}/cd"),
    )


def operate(
    environment: str, action: str, payload: dict[str, Any], approved: str = ""
) -> dict[str, Any]:
    if environment not in {"staging", "production"} or action not in {"plan", "apply"}:
        raise OperationError("explicit_release_target_required")
    config_path, root = locations(environment)
    config = config_file(config_path)
    expected_project = "muqola-staging" if environment == "staging" else "muqola-prod"
    if config["environment"] != environment or config["project"] != expected_project:
        raise OperationError("release_environment_mismatch")
    if payload.get("protocol") != 1:
        raise OperationError("controller_protocol_mismatch")
    endpoint = require_local_docker()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as locks:
        # Serialize heavy operations across both environments on a 4 GiB host.
        for path in (root.parent.parent / "cd.lock", root / "release.lock"):
            lock = locks.enter_context(path.open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise OperationError("release_in_progress") from error
        if endpoint:
            previous_endpoint = os.environ.get("DOCKER_HOST")
            if previous_endpoint is None:
                locks.callback(os.environ.pop, "DOCKER_HOST", None)
            else:
                locks.callback(os.environ.__setitem__, "DOCKER_HOST", previous_endpoint)
            os.environ["DOCKER_HOST"] = endpoint
            previous_name = os.environ.pop("DOCKER_CONTEXT", None)
            if previous_name is not None:
                locks.callback(os.environ.__setitem__, "DOCKER_CONTEXT", previous_name)
        # Registry credentials are short-lived; never argv, logs or persistent config.
        with tempfile.TemporaryDirectory(prefix="muqola-registry-") as directory:
            previous_context = os.environ.get("DOCKER_CONFIG")
            if previous_context is None:
                locks.callback(os.environ.pop, "DOCKER_CONFIG", None)
            else:
                locks.callback(os.environ.__setitem__, "DOCKER_CONFIG", previous_context)
            os.environ["DOCKER_CONFIG"] = directory
            token = payload.pop("registry_token")
            with tempfile.TemporaryFile() as secret:
                secret.write(token.encode())
                secret.seek(0)
                run(
                    [
                        "docker",
                        "login",
                        "ghcr.io",
                        "--username",
                        payload["registry_user"],
                        "--password-stdin",
                    ],
                    stdin=secret,
                )
            state = config_file(root / "state.json") if (root / "state.json").exists() else {}
            if action == "plan":
                plan = make_plan(config, payload, root, state)
                plan["nonce"] = secrets.token_hex(16)
                key = digest(plan)
                atomic_json(
                    root / "plans" / (key + ".json"),
                    {"created_at": utcnow().isoformat(), "plan": plan},
                )
                return {"hash": key, "plan": plan}
            return apply(config, payload, root, state, approved)


def main() -> int:
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("staging", "production"))
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--approved", default="")
    args = parser.parse_args()
    try:
        payload = json.loads(sys.stdin.buffer.read(65537))
        result = operate(args.environment, args.action, payload, args.approved)
        print(json.dumps(result))
        return 0
    except (OperationError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        code = (
            str(error)
            if isinstance(error, OperationError)
            else "release_failed_check_private_state"
        )
        print(json.dumps({"issues": [code]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
