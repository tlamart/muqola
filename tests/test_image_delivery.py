"""Trusted publication policy, exact candidate transfer and remote provenance refusals."""

import ast
import copy
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from deploy import image_provenance as provenance
from deploy.common import OperationError
from scripts import image_candidate as candidate

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64
CONFIG_BYTES = b'{"architecture":"amd64","os":"linux","config":{"User":"10001:10001"}}'
CONFIG_DIGEST = "sha256:" + hashlib.sha256(CONFIG_BYTES).hexdigest()
DIGEST = "sha256:" + "c" * 64
IMAGE = provenance.IMAGE_REPOSITORY + "@" + DIGEST


@pytest.fixture
def ci_context(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "GITHUB_REPOSITORY": provenance.REPOSITORY,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": COMMIT,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_WORKFLOW_REF": "tlamart/muqola/.github/workflows/ci.yml@refs/heads/main",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def policy(node: ast.AST, values: dict[str, str]) -> Any:
    if isinstance(node, ast.Expression):
        return policy(node.body, values)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return all(policy(value, values) for value in node.values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        return policy(node.left, values) == policy(node.comparators[0], values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        return values[ast.unparse(node)]
    raise AssertionError("Unexpected workflow publication policy")


def workflow() -> dict[str, Any]:
    return yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)  # type: ignore[no-any-return] # noqa: S506 -- BaseLoader constructs strings/collections only


@pytest.mark.parametrize(
    "event,ref,repository,result,allowed",
    [
        ("push", "refs/heads/main", "tlamart/muqola", "success", True),
        ("pull_request", "refs/pull/12/merge", "tlamart/muqola", "success", False),
        ("pull_request", "refs/heads/main", "tlamart/muqola", "success", False),
        ("pull_request_target", "refs/heads/main", "tlamart/muqola", "success", False),
        ("workflow_dispatch", "refs/heads/main", "tlamart/muqola", "success", False),
        ("push", "refs/heads/feature", "tlamart/muqola", "success", False),
        ("push", "refs/tags/main", "tlamart/muqola", "success", False),
        ("push", "refs/heads/main", "other/muqola", "success", False),
        ("push", "refs/heads/main", "tlamart/muqola", "failure", False),
        ("push", "refs/heads/main", "tlamart/muqola", "cancelled", False),
        ("push", "refs/heads/main", "tlamart/muqola", "skipped", False),
    ],
)
def test_actual_workflow_publication_guard(
    event: str, ref: str, repository: str, result: str, allowed: bool
) -> None:
    expression = workflow()["jobs"]["publish"]["if"].replace("&&", "and")
    assert (
        policy(
            ast.parse(expression, mode="eval"),
            {
                "github.event_name": event,
                "github.ref": ref,
                "github.repository": repository,
                "needs.checks.result": result,
            },
        )
        is allowed
    )


def test_workflow_scopes_permissions_and_transfers_by_same_run_artifact_id() -> None:
    document = workflow()
    assert document["permissions"] == {"contents": "read"}
    assert set(document["on"]) == {"pull_request", "push"}
    assert document["on"]["push"]["branches"] == ["main"]
    assert document["on"]["pull_request"]["branches"] == ["main"]
    checks, publish = document["jobs"]["checks"], document["jobs"]["publish"]
    assert publish["needs"] == "checks"
    assert (
        publish["env"]["CANDIDATE_CONFIG_DIGEST"]
        == "${{ needs.checks.outputs.candidate_config_digest }}"
    )
    assert (
        checks["outputs"]["candidate_config_digest"]
        == "${{ steps.export_candidate.outputs.config_digest }}"
    )
    assert publish["permissions"] == {"contents": "read", "packages": "write"}
    assert "permissions" not in checks and "environment" not in publish
    assert not any("SSH" in str(job) for job in document["jobs"].values())
    steps = publish["steps"]
    download = next(s for s in steps if s.get("uses", "").startswith("actions/download-artifact@"))
    assert download["with"]["artifact-ids"] == "${{ needs.checks.outputs.candidate_artifact_id }}"
    assert not {"run-id", "github-token"} & set(download["with"])
    commands = "\n".join(s.get("run", "") for s in steps)
    assert "docker build" not in commands and "compose" not in commands
    assert "scripts.image_candidate publish" in commands
    assert "--password-stdin" in commands and "docker logout" in commands
    build = next(s for s in checks["steps"] if s.get("id") == "build")
    assert build["run"].count("docker build ") == 1
    assert "docker compose up --no-build" in build["run"]
    exports = [
        i
        for i, step in enumerate(checks["steps"])
        if "image_candidate export" in step.get("run", "")
    ]
    last_check = next(
        i for i, s in enumerate(checks["steps"]) if "Codespaces HTTPS" in s.get("name", "")
    )
    assert len(exports) == 1 and exports[0] > last_check
    assert checks["steps"][exports[0]].get("if", "success()") == "success()"
    upload = next(s for s in checks["steps"] if s.get("id") == "upload_candidate")
    assert upload.get("if", "success()") == "success()"
    assert upload["with"]["if-no-files-found"] == "error"
    assert (
        checks["outputs"]["candidate_artifact_id"]
        == "${{ steps.upload_candidate.outputs.artifact-id }}"
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("GITHUB_REPOSITORY", "other/muqola"),
        ("GITHUB_WORKFLOW_REF", "tlamart/muqola/.github/workflows/other.yml@refs/heads/main"),
    ],
)
def test_script_refuses_untrusted_publication_before_docker(
    ci_context: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    commands: list[list[str]] = []
    monkeypatch.setattr(candidate, "run", lambda args: commands.append(args))
    with pytest.raises(OperationError):
        candidate.publish(tmp_path, IMAGE_ID, CONFIG_DIGEST, 42, tmp_path / "record")
    assert commands == []


def candidate_docker(args: list[str]) -> bytes:
    if args[:3] == ["docker", "image", "save"]:
        with tarfile.open(args[4], "w") as archive:
            for name, data in (
                ("manifest.json", b'[{"Config":"config.json","RepoTags":["muqola:local"]}]'),
                ("config.json", CONFIG_BYTES),
            ):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return b""
    if args[:3] == ["docker", "image", "inspect"]:
        return json.dumps(
            [
                {
                    "Id": IMAGE_ID,
                    "Os": "linux",
                    "Architecture": "amd64",
                    "RepoDigests": [IMAGE],
                    "Config": {
                        "User": "10001:10001",
                        "Labels": {
                            "org.opencontainers.image.revision": COMMIT,
                            "org.opencontainers.image.source": "https://github.com/tlamart/muqola",
                        },
                    },
                }
            ]
        ).encode()
    if args[:3] in (
        ["docker", "image", "load"],
        ["docker", "image", "tag"],
        ["docker", "image", "push"],
    ):
        return b""
    raise AssertionError(args)


def manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    return {"digest": DIGEST}, {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": CONFIG_DIGEST},
        "layers": [{"digest": "sha256:" + "d" * 64}],
    }


def test_exact_candidate_export_load_and_publish_without_build(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def docker(args: list[str]) -> bytes:
        commands.append(args)
        return candidate_docker(args)

    monkeypatch.setattr(candidate, "run", docker)
    monkeypatch.setattr(candidate, "registry_manifest", lambda _: manifest())
    exported = candidate.export(tmp_path, IMAGE_ID)
    assert exported["archive_sha256"] == candidate.archive_digest(tmp_path / "image.tar.gz")
    result = candidate.publish(tmp_path, IMAGE_ID, CONFIG_DIGEST, 42, tmp_path / "publication.json")
    provenance.validate_record(result, IMAGE, 123, 2)
    assert result["image_id"] == IMAGE_ID
    assert result["archive_sha256"] == exported["archive_sha256"]
    assert [cmd[-1] for cmd in commands if cmd[2] == "push"] == [
        "ghcr.io/tlamart/muqola:" + COMMIT + "-123-2",
        "ghcr.io/tlamart/muqola:" + COMMIT,
    ]
    assert all(cmd[3:5] == ["--platform", "linux/amd64"] for cmd in commands if cmd[2] == "push")
    assert not any("build" in cmd or "run" in cmd or "latest" in cmd for cmd in commands)


@pytest.mark.parametrize(
    "fault", ["archive", "image_id", "config_digest", "commit", "run_id", "run_attempt"]
)
def test_tampered_candidate_is_refused_before_load_or_push(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setattr(candidate, "run", candidate_docker)
    candidate.export(tmp_path, IMAGE_ID)
    if fault == "archive":
        (tmp_path / "image.tar.gz").write_bytes(b"different content")
    else:
        path = tmp_path / "candidate.json"
        data = json.loads(path.read_text())
        data[fault] = "incorrect"
        path.write_text(json.dumps(data))
    commands: list[list[str]] = []
    monkeypatch.setattr(candidate, "run", lambda args: commands.append(args))
    with pytest.raises(OperationError, match="candidate_transfer_mismatch"):
        candidate.load(tmp_path, IMAGE_ID, CONFIG_DIGEST)
    assert commands == []


@pytest.fixture
def evidence(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    record = {
        "schema": 1,
        "repository": "tlamart/muqola",
        "workflow": ".github/workflows/ci.yml",
        "event": "push",
        "ref": "refs/heads/main",
        "commit": COMMIT,
        "run_id": 123,
        "run_attempt": 2,
        "image": IMAGE,
        "image_id": IMAGE_ID,
        "config_digest": CONFIG_DIGEST,
        "platform": "linux/amd64",
        "candidate_artifact_id": 42,
        "archive_sha256": "sha256:" + "e" * 64,
    }
    run = {
        "id": 123,
        "repository": {"full_name": "tlamart/muqola"},
        "head_repository": {"full_name": "tlamart/muqola"},
        "event": "push",
        "head_branch": "main",
        "head_sha": COMMIT,
        "path": ".github/workflows/ci.yml",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
    }
    jobs = [
        {
            "name": name,
            "run_id": 123,
            "head_sha": COMMIT,
            "status": "completed",
            "conclusion": "success",
        }
        for name in ("checks", "publish")
    ]
    artifacts = [
        {
            "id": 456,
            "name": provenance.artifact_name(COMMIT, 2),
            "expired": False,
            "size_in_bytes": 1024,
            "workflow_run": {"id": 123, "head_sha": COMMIT},
        }
    ]
    values = {"run": run, "jobs": jobs, "artifacts": artifacts, "record": record}

    def api(self: object, path: str) -> dict[str, Any]:
        if "/jobs?" in path:
            return {"total_count": len(jobs), "jobs": jobs}
        if "/artifacts?" in path:
            return {"total_count": len(artifacts), "artifacts": artifacts}
        assert path == "actions/runs/123"
        return run

    monkeypatch.setattr(provenance.GitHubEvidence, "get", api)
    monkeypatch.setattr(provenance.GitHubEvidence, "record", lambda self, _: record)
    monkeypatch.setattr(provenance, "registry_manifest", lambda _: manifest())
    return values


def test_remote_evidence_and_manifest_allow_the_same_digest_for_both_environments(
    evidence: dict[str, Any],
) -> None:
    stage = provenance.verify(IMAGE, 123, 2)
    prod = provenance.verify(IMAGE, 123, 2)
    assert stage == prod == evidence["record"]


@pytest.mark.parametrize(
    "group,key,value",
    [
        ("run", "event", "pull_request"),
        ("run", "event", "workflow_dispatch"),
        ("run", "head_branch", "feature"),
        ("run", "repository", {"full_name": "fork/muqola"}),
        ("run", "head_repository", {"full_name": "fork/muqola"}),
        ("run", "conclusion", "failure"),
        ("run", "status", "in_progress"),
        ("run", "path", ".github/workflows/other.yml"),
        ("run", "run_attempt", 3),
        ("record", "commit", "f" * 40),
        ("record", "image", "ghcr.io/tlamart/muqola@sha256:" + "f" * 64),
        ("record", "image_id", "invalid-id"),
        ("record", "config_digest", "sha256:" + "f" * 64),
        ("record", "run_id", 124),
        ("record", "run_attempt", 1),
        ("record", "platform", "linux/arm64"),
        ("record", "candidate_artifact_id", "--unsafe"),
    ],
)
def test_inconsistent_remote_provenance_is_rejected(
    evidence: dict[str, Any], group: str, key: str, value: Any
) -> None:
    evidence[group][key] = value
    with pytest.raises(OperationError):
        provenance.verify(IMAGE, 123, 2)


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "expired", "wrong_run", "wrong_commit", "oversized"]
)
def test_absent_or_invalid_remote_artifacts_fail_closed(
    evidence: dict[str, Any], fault: str
) -> None:
    artifacts = evidence["artifacts"]
    if fault == "missing":
        artifacts.clear()
    elif fault == "duplicate":
        artifacts.append(copy.deepcopy(artifacts[0]))
    elif fault == "expired":
        artifacts[0]["expired"] = True
    elif fault == "wrong_run":
        artifacts[0]["workflow_run"]["id"] = 999
    elif fault == "wrong_commit":
        artifacts[0]["workflow_run"]["head_sha"] = "f" * 40
    else:
        artifacts[0]["size_in_bytes"] = 1000000
    with pytest.raises(OperationError):
        provenance.verify(IMAGE, 123, 2)


@pytest.mark.parametrize("job", ["checks", "publish"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_failed_checks_or_publication_is_not_provenance(
    evidence: dict[str, Any], job: str, result: str
) -> None:
    next(value for value in evidence["jobs"] if value["name"] == job)["conclusion"] = result
    with pytest.raises(OperationError, match="checks_and_publication_success_required"):
        provenance.verify(IMAGE, 123, 2)


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/tlamart/muqola:latest",
        "ghcr.io/tlamart/muqola:" + COMMIT,
        "ghcr.io/other/muqola@" + DIGEST,
        "ghcr.io/tlamart/muqola@" + DIGEST + ";echo bad",
    ],
)
def test_mutable_or_other_repository_reference_is_rejected_before_network(
    monkeypatch: pytest.MonkeyPatch, image: str
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(provenance, "run", lambda args: calls.append(args))
    with pytest.raises(OperationError, match="immutable_ghcr_image_required"):
        provenance.verify(image, 123, 2)
    assert calls == []


def test_unavailable_registry_and_wrong_manifest_are_rejected(
    evidence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent(_: str) -> Any:
        raise OperationError("command_failed")

    monkeypatch.setattr(provenance, "registry_manifest", absent)
    with pytest.raises(OperationError):
        provenance.verify(IMAGE, 123, 2)
    descriptor, document = manifest()
    descriptor["digest"] = "sha256:" + "f" * 64
    with pytest.raises(OperationError, match="published_manifest_mismatch"):
        provenance.validate_manifest(IMAGE, IMAGE_ID, descriptor, document)


@pytest.mark.parametrize("path", ["publication.json", "../publication.json", "extra.txt"])
def test_downloaded_archive_is_read_without_extracting_files(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = {"synthetic": "publication"}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(path, json.dumps(record))
    monkeypatch.setattr(provenance, "run", lambda _: archive.getvalue())
    if path == "publication.json":
        assert provenance.GitHubEvidence().record(456) == record
    else:
        with pytest.raises(OperationError, match="unexpected_publication_files"):
            provenance.GitHubEvidence().record(456)


@pytest.mark.parametrize("fault", ["user", "platform", "label"])
def test_loaded_image_identity_is_verified_before_any_push(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setattr(candidate, "run", candidate_docker)
    candidate.export(tmp_path, IMAGE_ID)
    commands: list[list[str]] = []

    def docker(args: list[str]) -> bytes:
        commands.append(args)
        value = candidate_docker(args)
        if args[:3] == ["docker", "image", "inspect"]:
            actual = json.loads(value)
            if fault == "user":
                actual[0]["Config"]["User"] = "root"
            elif fault == "platform":
                actual[0]["Architecture"] = "arm64"
            else:
                actual[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = "f" * 40
            return json.dumps(actual).encode()
        return value

    monkeypatch.setattr(candidate, "run", docker)
    with pytest.raises(OperationError, match="tested_candidate_identity_mismatch"):
        candidate.publish(tmp_path, IMAGE_ID, CONFIG_DIGEST, 42, tmp_path / "publication.json")
    assert not (tmp_path / "publication.json").exists()
    assert not any(cmd[2] in {"tag", "push"} for cmd in commands)


def test_failed_registry_push_never_writes_publication_evidence(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(candidate, "run", candidate_docker)
    candidate.export(tmp_path, IMAGE_ID)

    def fail(args: list[str]) -> bytes:
        if args[:3] == ["docker", "image", "push"]:
            raise OperationError("command_failed")
        return candidate_docker(args)

    monkeypatch.setattr(candidate, "run", fail)
    with pytest.raises(OperationError, match="command_failed"):
        candidate.publish(tmp_path, IMAGE_ID, CONFIG_DIGEST, 42, tmp_path / "publication.json")
    assert not (tmp_path / "publication.json").exists()


def test_cross_store_engine_ids_are_allowed_only_with_the_exact_tested_configuration(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(candidate, "run", candidate_docker)
    exported = candidate.export(tmp_path, IMAGE_ID)
    assert exported["config_digest"] == CONFIG_DIGEST != IMAGE_ID

    def different_store(args: list[str]) -> bytes:
        value = candidate_docker(args)
        if args[:3] == ["docker", "image", "inspect"]:
            actual = json.loads(value)
            actual[0]["Id"] = "sha256:" + "f" * 64
            return json.dumps(actual).encode()
        return value

    monkeypatch.setattr(candidate, "run", different_store)
    assert candidate.load(tmp_path, IMAGE_ID, CONFIG_DIGEST) == exported


def test_loaded_configuration_must_match_even_when_engine_inspection_passes(
    ci_context: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(candidate, "run", candidate_docker)
    candidate.export(tmp_path, IMAGE_ID)

    def changed_configuration(args: list[str]) -> bytes:
        value = candidate_docker(args)
        if args[:3] == ["docker", "image", "save"]:
            with tarfile.open(args[4], "w") as archive:
                for name, data in (
                    ("manifest.json", b'[{"Config":"config.json"}]'),
                    ("config.json", CONFIG_BYTES + b" "),
                ):
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
        return value

    monkeypatch.setattr(candidate, "run", changed_configuration)
    with pytest.raises(OperationError, match="loaded_configuration_mismatch"):
        candidate.load(tmp_path, IMAGE_ID, CONFIG_DIGEST)
