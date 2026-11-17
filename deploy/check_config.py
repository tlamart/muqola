"""Read-only production Compose preflight; never starts or changes containers."""

import argparse
import json
import re
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from deploy.common import OperationError, compose, config_file, run

IMAGE = re.compile(r"ghcr\.io/tlamart/muqola@sha256:[0-9a-f]{64}\Z")


def validate(document: dict[str, Any], project: str) -> list[str]:
    issues = []
    if document.get("name") != project:
        issues.append("project_mismatch")
    services = document.get("services", {})
    if set(services) != {"web", "worker", "db", "migrate"}:
        issues.append("unexpected_services")
    for name, service in services.items():
        if service.get("build") or service.get("ports") or service.get("network_mode"):
            issues.append("build_or_published_ports_or_network_mode")
        if service.get("privileged"):
            issues.append("privileged_container")
        networks = set(service.get("networks", {}))
        if networks != ({"private", "proxy"} if name == "web" else {"private"}):
            issues.append("network_isolation")
        if name != "db":
            if not IMAGE.fullmatch(service.get("image", "")):
                issues.append("immutable_ghcr_image_required")
            environment = service.get("environment", {})
            expected_role = "muqola_migrate" if name == "migrate" else "muqola_app"
            if (
                environment.get("APP_ENV") != "production"
                or environment.get("POSTGRES_USER") != expected_role
            ):
                issues.append("production_runtime_or_database_role")
            try:
                for peer in environment.get("TRUSTED_PROXY_IPS", "").split(","):
                    if "/" in peer or "%" in peer:
                        raise ValueError
                    ip_address(peer.strip())
            except ValueError:
                issues.append("exact_trusted_proxy_required")
    proxy = document.get("networks", {}).get("proxy", {})
    if not proxy.get("external") or not proxy.get("name"):
        issues.append("external_proxy_network_required")
    aliases = services.get("web", {}).get("networks", {}).get("proxy", {}).get("aliases", [])
    if aliases != ["muqola-web"]:
        issues.append("unique_web_alias_required")
    private = document.get("networks", {}).get("private", {})
    if private.get("external") or private.get("name") == proxy.get("name"):
        issues.append("private_network_required")
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Private operator JSON with project/compose_env/compose_file",
    )
    args = parser.parse_args()
    try:
        config = config_file(args.config)
        command = [*compose(config), "--profile", "maintenance", "config", "--format", "json"]
        issues = validate(json.loads(run(command)), config["project"])
    except (OSError, KeyError, ValueError, TypeError, AttributeError, OperationError):
        issues = ["configuration_unavailable"]
    print(json.dumps({"issues": issues}))
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
