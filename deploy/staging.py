"""Guarded staging lifecycle: no builds, migrations, data imports or volume removal."""

import argparse
import fcntl
import json
import os
import shutil
from pathlib import Path
from typing import Any

from deploy.check_config import validate
from deploy.common import OperationError, atomic_json, compose, config_file, run, utcnow
from deploy.probe import load_credentials, private_access_blocked, protected_probe
from deploy.staging_config import isolation_issues

MIB = 1024**2


def require_local_docker() -> None:
    if not os.environ.get("DOCKER_HOST", "unix://").startswith("unix://"):
        raise OperationError("local_docker_required")
    endpoint = json.loads(
        run(["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"])
    )
    if not isinstance(endpoint, str) or not endpoint.startswith("unix://"):
        raise OperationError("local_docker_required")


def host_resources(data_path: str) -> dict[str, int | float]:
    require_local_docker()
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]))
    cpus = max(1, min(os.cpu_count() or 1, int(info.get("NCPU", 1))))
    return {
        "available_memory_bytes": values["MemAvailable"],
        "free_disk_bytes": shutil.disk_usage(data_path).free,
        "load_per_core": os.getloadavg()[0] / cpus,
        "cpu_count": cpus,
        "limits_enforced": bool(
            info.get("MemoryLimit")
            and info.get("CpuCfsQuota")
            and info.get("CgroupDriver") != "none"
        ),
    }


def capacity_issues(
    document: dict[str, Any], config: dict[str, Any], measured: dict[str, int | float]
) -> tuple[list[str], int]:
    services = document["services"]
    memory = sum(int(s["mem_limit"]) for name, s in services.items() if name != "migrate")
    memory += int(services["migrate"]["mem_limit"])  # Reserve maintenance capacity too.
    margin = int(config.get("memory_margin_bytes", 512 * MIB))
    if margin < 256 * MIB:
        raise OperationError("capacity_margin_too_small")
    required = memory + margin
    issues = []
    if measured.get("limits_enforced") is not True:
        issues.append("resource_limits_not_enforced")
    if measured["available_memory_bytes"] < required:
        issues.append("insufficient_available_memory")
    if measured["free_disk_bytes"] < max(
        1024**3, int(config.get("min_free_disk_bytes", 2 * 1024**3))
    ):
        issues.append("insufficient_disk")
    limit = float(config.get("max_load_per_core", 0.75))
    if not 0 < limit <= 1 or measured["load_per_core"] > limit:
        issues.append("insufficient_cpu_headroom")
    if config.get("capacity_reviewed") is not True:
        issues.append("capacity_review_required")
    return issues, required


def rendered(config: dict[str, Any]) -> dict[str, Any]:
    return json.loads(run([*compose(config), "--profile", "*", "config", "--format", "json"]))  # type: ignore[no-any-return]


def preflight(config: dict[str, Any]) -> dict[str, Any]:
    if (
        config.get("environment") != "staging"
        or config.get("project") != "muqola-staging"
        or Path(config["compose_file"]).name != "compose.staging.yaml"
    ):
        raise OperationError("explicit_staging_target_required")
    if config.get("app_url") != "https://staging.muqola.tlam.art":
        raise OperationError("staging_probe_origin_required")
    require_local_docker()
    document = rendered(config)
    issues = validate(document, "muqola-staging", environment="staging")
    prod_config = config_file(Path(config["production_config"]))
    if (
        prod_config.get("project") != "muqola-prod"
        or prod_config.get("environment", "production") != "production"
    ):
        raise OperationError("production_reference_required")
    prod_document = rendered(prod_config)
    issues += validate(prod_document, "muqola-prod")
    issues += isolation_issues(prod_document, document, material=True)
    if config.get("synthetic_data_only") is not True:
        issues.append("synthetic_data_confirmation_required")
    # Verify private access credentials exist without publishing them.
    load_credentials(Path(config["probe_credentials_file"]))
    measured = host_resources(config["data_path"])
    capacity_problems, required = capacity_issues(document, config, measured)
    issues += capacity_problems
    return {
        "issues": sorted(set(issues)),
        "measured": measured,
        "required_available_memory_bytes": required,
    }


def operate(config: dict[str, Any], action: str) -> dict[str, Any]:
    # Stop/status remain usable when review is pending or production secrets unavailable.
    if (
        config.get("environment") != "staging"
        or config.get("project") != "muqola-staging"
        or Path(config["compose_file"]).name != "compose.staging.yaml"
    ):
        raise OperationError("explicit_staging_target_required")
    require_local_docker()
    command = compose(config)
    if action == "stop":
        run([*command, "stop", "--timeout", "30", "web", "worker", "mailpit", "db"])
        return {"action": "stopped", "volumes_preserved": True}
    if action == "status":
        raw = run([*command, "ps", "--all", "--format", "json"]).decode()
        try:
            values = json.loads(raw)
        except ValueError:
            values = [json.loads(line) for line in raw.splitlines() if line]
        if isinstance(values, dict):
            values = [values]
        return {
            "containers": [
                {key: item.get(key) for key in ("Service", "State", "Health")} for item in values
            ]
        }
    result = preflight(config)
    if action == "check":
        return result
    if result["issues"]:
        return result | {"action": "start_refused"}
    if not private_access_blocked(config["app_url"].rstrip("/") + "/health/ready/"):
        raise OperationError("staging_access_not_private")
    run([*command, "up", "-d", "--no-build", "--wait", "db", "mailpit"])
    try:
        # Apply nothing here. Operator must review/run the existing migration task separately.
        run(
            [
                *command,
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                "python",
                "manage.py",
                "migrate",
                "--check",
            ]
        )
    except OperationError as error:
        raise OperationError("pending_migrations_require_review") from error
    run([*command, "run", "--rm", "--no-deps", "web", "python", "manage.py", "staging_readiness"])
    run([*command, "up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "web", "worker"])
    if not protected_probe(
        config["app_url"].rstrip("/") + "/health/ready/", Path(config["probe_credentials_file"])
    ):
        raise OperationError("staging_https_not_ready")
    return result | {"action": "started"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "start", "stop", "status"))
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    can_record = False
    try:
        config = config_file(args.config)
        state = Path(config["state_file"]).resolve()
        if state.name != "state.json" or not (
            {"staging", "muqola-staging"} & set(state.parent.parts)
        ):
            raise OperationError("staging_state_path_required")
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(state.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise OperationError("staging_operation_in_progress") from error
            can_record = True
            result = operate(config, args.action)
            if args.action in {"start", "stop"}:
                atomic_json(state, {"time": utcnow().isoformat(), **result})
        print(json.dumps(result))
        return int(bool(result.get("issues")))
    except (OSError, ValueError, TypeError, KeyError, OperationError) as error:
        code = str(error) if isinstance(error, OperationError) else "staging_operation_failed"
        if args.action in {"start", "stop"} and can_record:
            try:
                atomic_json(
                    state,
                    {
                        "time": utcnow().isoformat(),
                        "action": args.action + "_failed",
                        "issues": [code],
                    },
                )
            except OSError:
                pass
        print(json.dumps({"issues": [code]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
