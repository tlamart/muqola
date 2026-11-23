"""Deploy a successful main publication to staging; production has no automatic path."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from deploy.common import OperationError, atomic_json
from deploy.delivery import transport
from deploy.image_provenance import (
    REPOSITORY,
    SHA,
    WORKFLOW,
    GitHubEvidence,
    artifact_name,
    positive,
    verify,
)
from deploy.release import digest


def source_run(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("workflow_run", {})
    if (
        os.environ.get("GITHUB_EVENT_NAME") != "workflow_run"
        or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_WORKFLOW_REF")
        != f"{REPOSITORY}/.github/workflows/staging.yml@refs/heads/main"
        or event.get("action") != "completed"
        or event.get("repository", {}).get("full_name") != REPOSITORY
        or source.get("head_repository", {}).get("full_name") != REPOSITORY
        or source.get("repository", {}).get("full_name") != REPOSITORY
        or source.get("event") != "push"
        or source.get("head_branch") != "main"
        or source.get("path") != WORKFLOW
        or source.get("status") != "completed"
        or source.get("conclusion") != "success"
        or not SHA.fullmatch(str(source.get("head_sha", "")))
    ):
        raise OperationError("successful_main_workflow_run_required")
    positive(source.get("id"))
    positive(source.get("run_attempt"))
    return source  # type: ignore[no-any-return]


def current_main(evidence: GitHubEvidence, commit: str) -> bool:
    head = evidence.get("git/ref/heads/main")["object"]["sha"]
    if not SHA.fullmatch(str(head)):
        raise OperationError("invalid_main_reference")
    return bool(head == commit)


def deploy(event: dict[str, Any]) -> dict[str, Any]:
    source = source_run(event)
    evidence = GitHubEvidence()
    commit, run_id, attempt = source["head_sha"], source["id"], source["run_attempt"]
    if not current_main(evidence, commit):
        return {"phase": "skipped", "reason": "superseded_main", "commit": commit}
    items = evidence.get(f"actions/runs/{run_id}/artifacts?per_page=100")
    matches = [
        item for item in items["artifacts"] if item["name"] == artifact_name(commit, attempt)
    ]
    if items["total_count"] > 100 or len(matches) != 1:
        raise OperationError("unique_publication_record_required")
    artifact = matches[0]
    if (
        artifact.get("expired") is not False
        or not 0 < artifact.get("size_in_bytes", 0) <= 65536
        or artifact.get("workflow_run", {}).get("id") != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != commit
    ):
        raise OperationError("publication_artifact_unavailable")
    record = evidence.record(positive(artifact["id"]))
    publication = verify(record["image"], run_id, attempt)
    if publication["commit"] != commit:
        raise OperationError("publication_commit_mismatch")
    # Recheck after provenance calls and immediately before touching the host.
    if not current_main(evidence, commit):
        return {"phase": "skipped", "reason": "superseded_main", "commit": commit}
    args = argparse.Namespace(
        environment="staging",
        action="plan",
        kind="deploy",
        image=publication["image"],
        plan_hash="",
    )
    plan = transport(args, publication)
    # Defense in depth: only the exact plan produced in this execution is applied.
    if (
        plan["hash"] != digest(plan["plan"])
        or plan["plan"].get("environment") != "staging"
        or plan["plan"].get("kind") != "deploy"
        or plan["plan"].get("image") != publication["image"]
        or plan["plan"].get("commit") != commit
    ):
        raise OperationError("automatic_staging_plan_mismatch")
    if verify(publication["image"], run_id, attempt) != publication:
        raise OperationError("publication_changed_after_plan")
    if not current_main(evidence, commit):
        return {"phase": "skipped", "reason": "superseded_main", "commit": commit}
    args.action, args.plan_hash = "apply", plan["hash"]
    result = transport(args, publication)
    if result.get("phase") != "succeeded" or result.get("image") != publication["image"]:
        raise OperationError("release_success_not_confirmed")
    return {**result, "commit": commit, "publication_run": run_id, "plan_hash": plan["hash"]}


def main() -> int:
    try:
        result = deploy(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()))
        atomic_json(Path("work/staging-result.json"), result)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        code = str(error) if isinstance(error, OperationError) else "staging_delivery_failed"
        result = {"phase": "failed", "issues": [code]}
        atomic_json(Path("work/staging-result.json"), result)
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
