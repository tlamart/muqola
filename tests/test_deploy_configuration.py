"""Render the actual production Compose; no daemon mutations or services started."""

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from deploy.check_config import validate
from deploy.common import OperationError, compose

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/tlamart/muqola@sha256:" + "a" * 64


@pytest.fixture
def production(tmp_path: Path) -> dict[str, Any]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose is required for configuration rendering")
    text = (
        (ROOT / ".env.production.example")
        .read_text()
        .replace("ghcr.io/tlamart/muqola@sha256:REPLACE_WITH_64_HEX_DIGEST", IMAGE)
        .replace("REPLACE_WITH_CADDY_CONTAINER_IP", "192.0.2.10")
    )
    env = tmp_path / "production.env"
    env.write_text(text)
    env.chmod(0o600)
    result = subprocess.run(  # noqa: S603 -- fixed read-only Compose command
        [
            docker,
            "compose",
            "--env-file",
            str(env),
            "-f",
            str(ROOT / "compose.prod.yaml"),
            "--profile",
            "maintenance",
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def test_shared_proxy_has_no_ports_and_no_database_access(production: dict[str, Any]) -> None:
    assert validate(production, "muqola-prod") == []
    services = production["services"]
    assert set(services) == {"web", "worker", "migrate", "db"}
    assert set(services["web"]["networks"]) == {"private", "proxy"}
    assert services["web"]["networks"]["proxy"]["aliases"] == ["muqola-web"]
    assert production["networks"]["proxy"]["name"] == "proxy"
    assert production["networks"]["proxy"]["external"] is True
    assert production["volumes"]["postgres_data"]["name"] == "muqola-prod_postgres_data"
    for name, service in services.items():
        assert not service.get("ports") and not service.get("build")
        if name != "web":
            assert set(service["networks"]) == {"private"}
    for name in ("web", "worker", "migrate"):
        assert services[name]["read_only"]
        assert services[name]["cap_drop"] == ["ALL"]
        assert services[name]["environment"]["APP_ENV"] == "production"
        secret_names = {value["source"] for value in services[name]["secrets"]}
        assert "db_admin_password" not in secret_names
        assert ("db_migrate_password" in secret_names) is (name == "migrate")
    assert services["migrate"]["environment"]["POSTGRES_USER"] == "muqola_migrate"
    assert services["web"]["environment"]["POSTGRES_USER"] == "muqola_app"
    assert "maintenance" in services["migrate"]["profiles"]
    assert "healthcheck" in services["worker"]


@pytest.mark.parametrize(
    "image",
    ["muqola:local", "ghcr.io/tlamart/muqola:latest", "ghcr.io/other/muqola@sha256:" + "a" * 64],
)
def test_preflight_rejects_tags_and_other_repositories(
    production: dict[str, Any], image: str
) -> None:
    production["services"]["web"]["image"] = image
    assert "immutable_ghcr_image_required" in validate(production, "muqola-prod")


def test_preflight_refuses_exposure_and_wrong_project(production: dict[str, Any]) -> None:
    changed = copy.deepcopy(production)
    changed["services"]["db"]["networks"]["proxy"] = {}
    changed["services"]["db"]["ports"] = [{"published": "5432", "target": 5432}]
    changed["services"]["worker"]["build"] = {"context": "."}
    assert set(validate(changed, "another-project")) >= {
        "project_mismatch",
        "network_isolation",
        "build_or_published_ports_or_network_mode",
    }


def test_operations_require_explicit_project_and_private_environment(tmp_path: Path) -> None:
    env = tmp_path / "env"
    env.write_text("APP_DOMAIN=synthetic.example.test")
    env.chmod(0o600)
    config = {"compose_env": str(env), "compose_file": "compose.prod.yaml"}
    with pytest.raises(OperationError, match="explicit_compose_project"):
        compose(config)
    with pytest.raises(OperationError):
        compose(config | {"project": "--project-directory"})
    command = compose(config | {"project": "muqola-prod"})
    assert command[2:4] == ["--project-name", "muqola-prod"]
    env.chmod(0o644)
    with pytest.raises(OperationError, match="private_file_permissions"):
        compose(config | {"project": "muqola-prod"})


def test_preflight_refuses_broad_trust_and_privileged_database_role(
    production: dict[str, Any],
) -> None:
    production["services"]["web"]["environment"].update(
        TRUSTED_PROXY_IPS="192.0.2.0/24", POSTGRES_USER="muqola_admin"
    )
    assert set(validate(production, "muqola-prod")) >= {
        "exact_trusted_proxy_required",
        "production_runtime_or_database_role",
    }
