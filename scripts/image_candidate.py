"""Transfer the exact tested image between CI jobs; publish only from trusted main."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from deploy.common import OperationError, atomic_json, run
from deploy.image_provenance import (
    DIGEST,
    IMAGE_REPOSITORY,
    REPOSITORY,
    SHA,
    WORKFLOW,
    artifact_name,
    positive,
    registry_manifest,
    validate_manifest,
    validate_record,
)


def context(*, publishing: bool = False) -> dict[str, Any]:
    repository, event, ref = (
        os.environ.get("GITHUB_REPOSITORY"),
        os.environ.get("GITHUB_EVENT_NAME"),
        os.environ.get("GITHUB_REF"),
    )
    commit = os.environ.get("GITHUB_SHA", "")
    if repository != REPOSITORY or not SHA.fullmatch(commit):
        raise OperationError("trusted_repository_and_commit_required")
    if publishing and (
        event != "push"
        or ref != "refs/heads/main"
        or os.environ.get("GITHUB_WORKFLOW_REF") != f"{REPOSITORY}/{WORKFLOW}@refs/heads/main"
    ):
        raise OperationError("main_push_publication_only")
    return {
        "schema": 1,
        "repository": repository,
        "workflow": WORKFLOW,
        "ref": ref,
        "event": event,
        "commit": commit,
        "run_id": positive(os.environ.get("GITHUB_RUN_ID")),
        "run_attempt": positive(os.environ.get("GITHUB_RUN_ATTEMPT")),
    }


def inspect_candidate(image_id: str, commit: str) -> None:
    if not DIGEST.fullmatch(image_id):
        raise OperationError("candidate_image_id_required")
    image = json.loads(run(["docker", "image", "inspect", "muqola:local"]))[0]
    labels = image.get("Config", {}).get("Labels") or {}
    if (
        image.get("Id") != image_id
        or image.get("Os") != "linux"
        or image.get("Architecture") != "amd64"
        or image.get("Config", {}).get("User") != "10001:10001"
        or labels.get("org.opencontainers.image.revision") != commit
        or labels.get("org.opencontainers.image.source") != f"https://github.com/{REPOSITORY}"
    ):
        raise OperationError("tested_candidate_identity_mismatch")


def archive_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def export(directory: Path, image_id: str) -> dict[str, Any]:
    # Docker load supports gzip; one artifact is transferred, never rebuilt.
    import gzip
    import shutil

    source = context()
    inspect_candidate(image_id, source["commit"])
    directory.mkdir(parents=True, exist_ok=True)
    tar, archive = directory / "image.tar", directory / "image.tar.gz"
    run(["docker", "image", "save", "--output", str(tar), "muqola:local"])
    with tar.open("rb") as original, gzip.open(archive, "wb", compresslevel=1) as compressed:
        shutil.copyfileobj(original, compressed)
    tar.unlink()
    candidate = source | {
        "image_id": image_id,
        "platform": "linux/amd64",
        "archive_sha256": archive_digest(archive),
    }
    atomic_json(directory / "candidate.json", candidate)
    return candidate


def load(directory: Path, image_id: str, *, publishing: bool = True) -> dict[str, Any]:
    source = context(publishing=publishing)
    candidate = json.loads((directory / "candidate.json").read_text())
    if (
        any(candidate.get(key) != value for key, value in source.items())
        or candidate.get("image_id") != image_id
        or not DIGEST.fullmatch(image_id)
        or candidate.get("platform") != "linux/amd64"
        or candidate.get("archive_sha256") != archive_digest(directory / "image.tar.gz")
    ):
        raise OperationError("candidate_transfer_mismatch")
    run(["docker", "image", "load", "--input", str(directory / "image.tar.gz")])
    inspect_candidate(image_id, source["commit"])
    return candidate  # type: ignore[no-any-return]


def publish(
    directory: Path, image_id: str, candidate_artifact_id: int, output: Path
) -> dict[str, Any]:
    # Guard before docker load, tag or push even when invoked outside the workflow.
    source = context(publishing=True)
    candidate_artifact_id = positive(candidate_artifact_id)
    candidate = load(directory, image_id)
    # Keep an additional run tag so a SHA-tag update never discards the older image's last tag.
    tags = [
        f"{IMAGE_REPOSITORY}:{source['commit']}-{source['run_id']}-{source['run_attempt']}",
        f"{IMAGE_REPOSITORY}:{source['commit']}",
    ]
    for tag in tags:
        run(["docker", "image", "tag", image_id, tag])
        run(["docker", "image", "push", tag])
    actual = json.loads(run(["docker", "image", "inspect", tags[-1]]))[0]
    references = {
        value
        for value in actual.get("RepoDigests", [])
        if value.startswith(IMAGE_REPOSITORY + "@sha256:")
    }
    if len(references) != 1 or actual.get("Id") != image_id:
        raise OperationError("published_digest_unavailable")
    image = references.pop()
    record = candidate | {"image": image, "candidate_artifact_id": candidate_artifact_id}
    validate_record(record, image, source["run_id"], source["run_attempt"])
    descriptor, manifest = registry_manifest(image)
    validate_manifest(image, image_id, descriptor, manifest)
    atomic_json(output, record)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as stream:
            stream.write(
                f"Image testée publiée : `{image}`\n\n"
                f"Commit : `{source['commit']}` ; run `{source['run_id']}`, "
                f"tentative `{source['run_attempt']}`.\n\n"
                f"Preuve : `{artifact_name(source['commit'], source['run_attempt'])}`. "
                "Attendre le succès complet du workflow avant vérification/promotion.\n"
            )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "publish"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--candidate-artifact-id", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "export":
            result = export(args.directory, args.image_id)
        else:
            if args.candidate_artifact_id is None or args.output is None:
                raise OperationError("publication_arguments_required")
            result = publish(args.directory, args.image_id, args.candidate_artifact_id, args.output)
        print(json.dumps(result))
        return 0
    except (OperationError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        code = str(error) if isinstance(error, OperationError) else "candidate_operation_failed"
        print(json.dumps({"issues": [code]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
