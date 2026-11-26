"""Automatic staging cannot accept PRs, foreign publications or production plans."""

import argparse
import ast
import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from deploy import delivery, staging_delivery
from deploy.common import OperationError
from deploy.release import digest
from tests.test_image_delivery import policy

COMMIT = "a" * 40
IMAGE = "ghcr.io/tlamart/muqola@sha256:" + "b" * 64


@pytest.fixture
def automatic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.chdir(tmp_path)
    for key, setting in {
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "tlamart/muqola",
        "GITHUB_WORKFLOW_REF": "tlamart/muqola/.github/workflows/staging.yml@refs/heads/main",
    }.items():
        monkeypatch.setenv(key, setting)
    event = {
        "action": "completed",
        "repository": {"full_name": "tlamart/muqola"},
        "workflow_run": {
            "id": 123,
            "run_attempt": 2,
            "repository": {"full_name": "tlamart/muqola"},
            "head_repository": {"full_name": "tlamart/muqola"},
            "head_branch": "main",
            "head_sha": COMMIT,
            "event": "push",
            "path": ".github/workflows/ci.yml",
            "status": "completed",
            "conclusion": "success",
        },
    }
    artifact = {
        "id": 456,
        "name": f"muqola-publication-{COMMIT}-2",
        "expired": False,
        "size_in_bytes": 1024,
        "workflow_run": {"id": 123, "head_sha": COMMIT},
    }
    plan = {
        "environment": "staging",
        "kind": "deploy",
        "image": IMAGE,
        "commit": COMMIT,
        "nonce": "c" * 32,
    }
    value: dict[str, Any] = {
        "event": event,
        "artifact": artifact,
        "artifacts": {"total_count": 1, "artifacts": [artifact]},
        "publication": {"image": IMAGE, "commit": COMMIT},
        "plan": {"hash": digest(plan), "plan": plan},
        "commands": [],
        "refs": [COMMIT, COMMIT, COMMIT],
        "verified": [],
    }

    def get(self: Any, path: str) -> dict[str, Any]:
        if path == "git/ref/heads/main":
            return {"object": {"sha": value["refs"].pop(0)}}
        assert path == "actions/runs/123/artifacts?per_page=100"
        return value["artifacts"]  # type: ignore[no-any-return]

    def verify(image: str, run_id: int, attempt: int) -> dict[str, Any]:
        value["verified"].append((image, run_id, attempt))
        return value["publication"]  # type: ignore[no-any-return]

    def transport(args: argparse.Namespace, publication: dict[str, Any]) -> dict[str, Any]:
        value["commands"].append(copy.copy(args))
        assert publication == value["publication"]
        if args.action == "plan":
            return value["plan"]  # type: ignore[no-any-return]
        return {"phase": "succeeded", "image": IMAGE, "schema": "d" * 64}

    monkeypatch.setattr("deploy.staging_delivery.GitHubEvidence.get", get)
    monkeypatch.setattr(
        "deploy.staging_delivery.GitHubEvidence.record",
        lambda self, identifier: value["publication"],
    )
    monkeypatch.setattr(staging_delivery, "verify", verify)
    monkeypatch.setattr(staging_delivery, "transport", transport)
    return value


def test_same_verified_digest_is_planned_and_applied_without_manual_inputs(
    automatic: dict[str, Any],
) -> None:
    result = staging_delivery.deploy(automatic["event"])
    assert result["phase"] == "succeeded" and result["publication_run"] == 123
    assert automatic["verified"] == [(IMAGE, 123, 2), (IMAGE, 123, 2)]
    first, second = automatic["commands"]
    assert first.environment == second.environment == "staging"
    assert first.kind == second.kind == "deploy"
    assert first.image == second.image == IMAGE
    assert first.action == "plan" and second.action == "apply"
    assert second.plan_hash == automatic["plan"]["hash"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("event", "pull_request"),
        ("event", "pull_request_target"),
        ("event", "workflow_dispatch"),
        ("head_branch", "feature"),
        ("head_repository", {"full_name": "foreign/muqola"}),
        ("repository", {"full_name": "foreign/muqola"}),
        ("head_sha", "untrusted"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "cancelled"),
        ("path", ".github/workflows/other.yml"),
        ("id", True),
        ("run_attempt", 0),
    ],
)
def test_untrusted_trigger_is_rejected_before_host_access(
    automatic: dict[str, Any], key: str, value: Any
) -> None:
    automatic["event"]["workflow_run"][key] = value
    with pytest.raises(OperationError):
        staging_delivery.deploy(automatic["event"])
    assert not automatic["commands"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REPOSITORY", "foreign/muqola"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_WORKFLOW_REF", "tlamart/muqola/.github/workflows/deploy.yml@refs/heads/main"),
    ],
)
def test_wrong_execution_context_is_rejected(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    with pytest.raises(OperationError):
        staging_delivery.deploy(automatic["event"])
    assert not automatic["commands"]


@pytest.mark.parametrize("when", [0, 1, 2])
def test_newer_main_skips_old_image_before_plan_or_apply(
    automatic: dict[str, Any], when: int
) -> None:
    automatic["refs"][when] = "e" * 40
    assert staging_delivery.deploy(automatic["event"])["phase"] == "skipped"
    assert len(automatic["commands"]) == (1 if when == 2 else 0)


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "expired", "size", "run", "commit", "attempt", "page"]
)
def test_bad_publication_evidence_never_reaches_host(automatic: dict[str, Any], fault: str) -> None:
    artifact = automatic["artifact"]
    if fault == "missing":
        automatic["artifacts"]["artifacts"] = []
    elif fault == "duplicate":
        automatic["artifacts"]["artifacts"].append(copy.deepcopy(artifact))
    elif fault == "expired":
        artifact["expired"] = True
    elif fault == "size":
        artifact["size_in_bytes"] = 65537
    elif fault == "run":
        artifact["workflow_run"]["id"] = 999
    elif fault == "commit":
        artifact["workflow_run"]["head_sha"] = "f" * 40
    elif fault == "attempt":
        artifact["name"] = f"muqola-publication-{COMMIT}-1"
    else:
        automatic["artifacts"]["total_count"] = 101
    with pytest.raises(OperationError):
        staging_delivery.deploy(automatic["event"])
    assert not automatic["commands"]


def test_remote_provenance_failure_blocks_plan(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*args: Any) -> Any:
        raise OperationError("checks_and_publication_success_required")

    monkeypatch.setattr(staging_delivery, "verify", refused)
    with pytest.raises(OperationError, match="checks_and_publication_success_required"):
        staging_delivery.deploy(automatic["event"])
    assert not automatic["commands"]


def test_publication_rerun_after_plan_prevents_apply(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    original: Callable[..., dict[str, Any]] = staging_delivery.__dict__["verify"]
    calls = 0

    def verify(*args: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationError("successful_main_publication_required")
        return original(*args)

    monkeypatch.setattr(staging_delivery, "verify", verify)
    with pytest.raises(OperationError, match="successful_main_publication_required"):
        staging_delivery.deploy(automatic["event"])
    assert len(automatic["commands"]) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("environment", "production"),
        ("kind", "rollback"),
        ("image", "wrong"),
        ("commit", "e" * 40),
        ("nonce", "changed"),
    ],
)
def test_wrong_target_or_tampered_plan_is_never_applied(
    automatic: dict[str, Any], key: str, value: str
) -> None:
    automatic["plan"]["plan"][key] = value
    # Keep a valid hash for wrong targets to also exercise the target binding.
    if key != "nonce":
        automatic["plan"]["hash"] = digest(automatic["plan"]["plan"])
    with pytest.raises(OperationError, match="automatic_staging_plan_mismatch"):
        staging_delivery.deploy(automatic["event"])
    assert len(automatic["commands"]) == 1


@pytest.mark.parametrize("stage", ["plan", "apply"])
def test_controller_failure_is_not_retried_or_rolled_back(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    original: Callable[..., dict[str, Any]] = staging_delivery.__dict__["transport"]

    def transport(args: argparse.Namespace, publication: dict[str, Any]) -> dict[str, Any]:
        if args.action == stage:
            automatic["commands"].append(copy.copy(args))
            raise OperationError("host_gate_failed")
        return original(args, publication)

    monkeypatch.setattr(staging_delivery, "transport", transport)
    with pytest.raises(OperationError, match="host_gate_failed"):
        staging_delivery.deploy(automatic["event"])
    assert [c.action for c in automatic["commands"]] == (
        ["plan"] if stage == "plan" else ["plan", "apply"]
    )


def test_manual_command_still_rejects_automatic_event(automatic: dict[str, Any]) -> None:
    with pytest.raises(OperationError, match="manual_main_workflow_only"):
        delivery.deliver(argparse.Namespace(environment="production"))


def test_entrypoint_preserves_result_without_secrets(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(automatic["event"]))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    assert staging_delivery.main() == 0
    result = json.loads(Path("work/staging-result.json").read_text())
    assert result["image"] == IMAGE and result["plan_hash"] == automatic["plan"]["hash"]


def test_automatic_path_uses_existing_transport_and_exact_plan_hash(
    automatic: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    monkeypatch.setattr(staging_delivery, "transport", delivery.transport)
    monkeypatch.setattr(delivery, "ssh_options", lambda _: ("deploy@host.example.test", []))
    monkeypatch.setenv("GITHUB_ACTOR", "synthetic")
    monkeypatch.setenv("GH_TOKEN", "synthetic-token-never-in-argv")
    commands: list[list[str]] = []

    def run(args: list[str]) -> bytes:
        commands.append(args)
        if args[0] == "gh":
            name = args[-1].split("/contents/", 1)[1].split("?", 1)[0]
            content = b"synthetic asset"
            return json.dumps(
                {
                    "type": "file",
                    "path": name,
                    "size": len(content),
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode(),
                }
            ).encode()
        return b""

    def request(args: list[str], payload: Any) -> dict[str, Any]:
        commands.append(args)
        body = json.load(payload)
        assert body["publication"] == automatic["publication"]
        assert body["kind"] == "deploy"
        assert " production " not in args[-1]
        if args[-1].endswith("staging plan"):
            return automatic["plan"]  # type: ignore[no-any-return]
        assert args[-1].endswith("staging apply --approved " + automatic["plan"]["hash"])
        return {"phase": "succeeded", "image": IMAGE}

    monkeypatch.setattr(delivery, "run", run)
    monkeypatch.setattr(delivery, "remote_request", request)
    assert staging_delivery.deploy(automatic["event"])["phase"] == "succeeded"
    assert json.loads(Path("work/plan.json").read_text()) == automatic["plan"]
    assert "synthetic-token-never-in-argv" not in str(commands)


@pytest.mark.parametrize(
    "key,value",
    [
        ("github.event.workflow_run.event", "pull_request"),
        ("github.event.workflow_run.head_branch", "feature"),
        ("github.event.workflow_run.head_repository.full_name", "fork/muqola"),
        ("github.event.workflow_run.conclusion", "failure"),
        ("github.event.workflow_run.path", ".github/workflows/other.yml"),
        ("github.repository", "foreign/muqola"),
        ("github.repository", "tlamart/muqola"),
    ],
)
def test_actual_workflow_guard_and_production_boundary(key: str, value: str) -> None:
    path = Path(__file__).resolve().parents[1] / ".github/workflows/staging.yml"
    doc = yaml.load(path.read_text(), Loader=yaml.BaseLoader)  # noqa: S506 -- strings only
    assert doc["on"] == {
        "workflow_run": {
            "workflows": ["Muqola checks"],
            "branches": ["main"],
            "types": ["completed"],
        }
    }
    assert doc["concurrency"] == {"group": "delivery-staging", "cancel-in-progress": "false"}
    assert doc["permissions"] == {"contents": "read"}
    job = doc["jobs"]["staging"]
    assert job["environment"] == "staging"
    assert job["permissions"] == {"contents": "read", "actions": "read", "packages": "read"}
    values = {
        "github.repository": "tlamart/muqola",
        "github.event.workflow_run.event": "push",
        "github.event.workflow_run.head_branch": "main",
        "github.event.workflow_run.head_repository.full_name": "tlamart/muqola",
        "github.event.workflow_run.path": ".github/workflows/ci.yml",
        "github.event.workflow_run.conclusion": "success",
    }
    values[key] = value
    assert policy(ast.parse(job["if"].replace("&&", "and"), mode="eval"), values) is (
        value == "tlamart/muqola"
    )
    checkout = job["steps"][0]
    assert checkout["with"]["persist-credentials"] == "false" and "ref" not in checkout["with"]
    assert "python -m deploy.staging_delivery" in str(job["steps"])
