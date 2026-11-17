"""Additional staging isolation checks, without starting or changing services."""

import hashlib
from pathlib import Path
from typing import Any

from deploy.common import OperationError

MAILPIT_IMAGE = (
    "axllent/mailpit:v1.27@sha256:e22dce5b36f93c77082e204a3942fb6b283b7896e057458400a4c88344c3df68"
)


def staging_issues(document: dict[str, Any]) -> list[str]:
    issues = []
    services = document["services"]
    private = document.get("networks", {}).get("private", {})
    if not private.get("internal"):
        issues.append("staging_private_network_must_be_internal")
    volume = document.get("volumes", {}).get("postgres_data", {})
    if volume.get("external") or volume.get("name") != "muqola-staging_postgres_data":
        issues.append("staging_volume_identity")
    if document.get("name") != "muqola-staging":
        issues.append("staging_project_identity")
    data_mounts = [
        v
        for v in services.get("db", {}).get("volumes", [])
        if v.get("target") == "/var/lib/postgresql/data"
    ]
    if (
        len(data_mounts) != 1
        or data_mounts[0].get("type") != "volume"
        or data_mounts[0].get("source") != "postgres_data"
    ):
        issues.append("staging_database_mount")
    expected_secrets = {"django_key", "db_app_password", "db_admin_password", "db_migrate_password"}
    if set(document.get("secrets", {})) != expected_secrets:
        issues.append("staging_secrets_identity")
    images = set()
    for name, service in services.items():
        environment = service.get("environment", {})
        if name != "migrate" and "staging" not in service.get("profiles", []):
            issues.append("staging_must_be_opt_in")
        if service.get("restart") not in {"no", None}:
            issues.append("staging_restart_forbidden")
        if int(service.get("mem_limit", 0)) <= 0 or float(service.get("cpus", 0)) <= 0:
            issues.append("staging_resource_limits_required")
        if name == "mailpit":
            if service.get("image") != MAILPIT_IMAGE:
                issues.append("staging_capture_image")
            allowed = {"MP_MAX_MESSAGES", "MP_SMTP_AUTH_ACCEPT_ANY", "MP_DISABLE_VERSION_CHECK"}
            if set(environment) - allowed or environment.get("MP_SMTP_AUTH_ACCEPT_ANY") != "false":
                issues.append("staging_capture_relay_forbidden")
        else:
            if environment.get("POSTGRES_DB") != "muqola_staging":
                issues.append("staging_database_identity")
        if name in {"web", "worker", "migrate"}:
            images.add(service.get("image"))
            if (
                environment.get("POSTGRES_HOST") != "db"
                or environment.get("DEPLOYMENT_ENV") != "staging"
                or environment.get("APP_BASE_URL") != "https://staging.muqola.tlam.art"
                or environment.get("ALLOWED_HOSTS") != "staging.muqola.tlam.art"
            ):
                issues.append("staging_origin_or_context")
            if (
                environment.get("EMAIL_HOST") != "mailpit"
                or str(environment.get("EMAIL_PORT")) != "1025"
                or environment.get("EMAIL_HOST_USER")
                or environment.get("EMAIL_HOST_PASSWORD")
                or environment.get("EMAIL_HOST_PASSWORD_FILE")
                or environment.get("EMAIL_USE_TLS") != "false"
                or environment.get("EMAIL_USE_SSL") != "false"
            ):
                issues.append("staging_capture_only")
            if "smtp_password" in {item["source"] for item in service.get("secrets", [])}:
                issues.append("staging_smtp_secret_forbidden")
    if len(images) != 1:
        issues.append("same_staging_image_required")
    return issues


def isolation_issues(
    production: dict[str, Any], staging: dict[str, Any], *, material: bool = False
) -> list[str]:
    issues = []
    if production.get("name") == staging.get("name"):
        issues.append("project_collision")
    for category in ("volumes",):
        prod_names = {v.get("name") for v in production.get(category, {}).values()}
        stage_names = {v.get("name") for v in staging.get(category, {}).values()}
        if prod_names & stage_names:
            issues.append("volume_collision")
    if production.get("networks", {}).get("private", {}).get("name") == staging.get(
        "networks", {}
    ).get("private", {}).get("name"):
        issues.append("private_network_collision")
    prod_files = {Path(s["file"]).resolve() for s in production.get("secrets", {}).values()}
    stage_files = {Path(s["file"]).resolve() for s in staging.get("secrets", {}).values()}
    if prod_files & stage_files:
        issues.append("secret_path_collision")
    prod_legal = {
        Path(v["source"]).resolve()
        for v in production["services"]["web"].get("volumes", [])
        if v.get("target") == "/app/legal"
    }
    stage_legal = {
        Path(v["source"]).resolve()
        for v in staging["services"]["web"].get("volumes", [])
        if v.get("target") == "/app/legal"
    }
    if prod_legal & stage_legal:
        issues.append("legal_mount_collision")
    if material:

        def fingerprints(paths: set[Path], minimum: int) -> list[bytes]:
            result = []
            for path in paths:
                if not path.is_file() or not minimum <= path.stat().st_size <= 16384:
                    raise OperationError("secret_material_unavailable")
                # Compose file secrets may be 0444 inside a 0700 directory.
                if path.stat().st_mode & 0o022:
                    raise OperationError("secret_material_writable")
                if path.stat().st_mode & 0o077 and path.parent.stat().st_mode & 0o077:
                    raise OperationError("secret_material_public")
                result.append(hashlib.sha256(path.read_bytes().rstrip(b"\r\n")).digest())
            return result

        production_hashes = fingerprints(prod_files, 1)
        staging_hashes = fingerprints(stage_files, 16)
        if set(production_hashes) & set(staging_hashes) or len(set(staging_hashes)) != len(
            staging_hashes
        ):
            issues.append("secret_material_reused")
    return sorted(set(issues))
