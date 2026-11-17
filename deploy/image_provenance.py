"""Verify a GHCR digest against a successful, trusted main publication run.

Read-only. Uses GitHub CLI authentication and Docker's registry credentials.
A local record, a SHA tag or an OCI label alone is never accepted as provenance.
"""

import argparse
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from deploy.common import OperationError, atomic_json, run

REPOSITORY = "tlamart/muqola"
IMAGE_REPOSITORY = "ghcr.io/" + REPOSITORY
WORKFLOW = ".github/workflows/ci.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE = re.compile(re.escape(IMAGE_REPOSITORY) + r"@sha256:[0-9a-f]{64}\Z")
MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}


def positive(value: object) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,19}", str(value)):
        raise OperationError("invalid_publication_identifier")
    return int(str(value))


def artifact_name(commit: str, attempt: int) -> str:
    if not SHA.fullmatch(commit):
        raise OperationError("invalid_source_commit")
    return f"muqola-publication-{commit}-{positive(attempt)}"


def validate_record(record: dict[str, Any], image: str, run_id: int, attempt: int) -> None:
    if not IMAGE.fullmatch(image):
        raise OperationError("immutable_ghcr_image_required")
    if (
        record.get("schema") != 1
        or record.get("repository") != REPOSITORY
        or record.get("workflow") != WORKFLOW
        or record.get("ref") != "refs/heads/main"
        or record.get("event") != "push"
        or record.get("run_id") != positive(run_id)
        or record.get("run_attempt") != positive(attempt)
        or record.get("image") != image
        or not SHA.fullmatch(str(record.get("commit", "")))
        or not DIGEST.fullmatch(str(record.get("image_id", "")))
        or not DIGEST.fullmatch(str(record.get("archive_sha256", "")))
        or record.get("platform") != "linux/amd64"
    ):
        raise OperationError("publication_record_mismatch")
    positive(record.get("candidate_artifact_id"))


def validate_manifest(
    image: str, image_id: str, descriptor: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if (
        not IMAGE.fullmatch(image)
        or descriptor.get("digest") != image.split("@")[-1]
        or manifest.get("schemaVersion") != 2
        or manifest.get("mediaType") not in MEDIA_TYPES
        or manifest.get("config", {}).get("digest") != image_id
        or not manifest.get("layers")
    ):
        raise OperationError("published_manifest_mismatch")


def registry_manifest(image: str) -> tuple[dict[str, Any], dict[str, Any]]:
    # Caller validates a deployable reference first; local smoke uses loopback only.
    prefix = ["docker", "buildx", "imagetools", "inspect"]
    descriptor = json.loads(run([*prefix, "--format", "{{json .Manifest}}", image]))
    manifest = json.loads(run([*prefix, "--raw", image]))
    return descriptor, manifest


class GitHubEvidence:
    """Fixed repository endpoints; gh handles TLS/auth without tokens in argv."""

    def get(self, suffix: str) -> dict[str, Any]:
        return json.loads(run(["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/{suffix}"]))  # type: ignore[no-any-return]

    def record(self, artifact_id: int) -> dict[str, Any]:
        archive = run(
            [
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{REPOSITORY}/actions/artifacts/{positive(artifact_id)}/zip",
            ]
        )
        if len(archive) > 65536:
            raise OperationError("publication_archive_too_large")
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as contents:
                if contents.namelist() != ["publication.json"]:
                    raise OperationError("unexpected_publication_files")
                entry = contents.getinfo("publication.json")
                if entry.file_size > 16384:
                    raise OperationError("publication_record_too_large")
                record = json.loads(contents.read(entry))
        except OperationError:
            raise
        except (zipfile.BadZipFile, RuntimeError) as error:
            raise OperationError("invalid_publication_archive") from error
        if not isinstance(record, dict):
            raise OperationError("invalid_publication_record")
        return record


def verify(image: str, run_id: int, attempt: int) -> dict[str, Any]:
    if not IMAGE.fullmatch(image):
        raise OperationError("immutable_ghcr_image_required")
    run_id, attempt = positive(run_id), positive(attempt)
    evidence = GitHubEvidence()
    source = evidence.get(f"actions/runs/{run_id}")
    if (
        source.get("id") != run_id
        or source.get("repository", {}).get("full_name") != REPOSITORY
        or source.get("head_repository", {}).get("full_name") != REPOSITORY
        or source.get("event") != "push"
        or source.get("head_branch") != "main"
        or source.get("path") != WORKFLOW
        or source.get("status") != "completed"
        or source.get("conclusion") != "success"
        or source.get("run_attempt") != attempt
        or not SHA.fullmatch(str(source.get("head_sha", "")))
    ):
        raise OperationError("successful_main_publication_required")
    jobs = evidence.get(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")
    values = jobs.get("jobs", [])
    if (
        jobs.get("total_count") != 2
        or len(values) != 2
        or {job.get("name") for job in values} != {"checks", "publish"}
        or any(
            job.get("run_id") != run_id
            or job.get("head_sha") != source["head_sha"]
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            for job in values
        )
    ):
        raise OperationError("checks_and_publication_success_required")
    artifacts = evidence.get(f"actions/runs/{run_id}/artifacts?per_page=100")
    if artifacts.get("total_count", 101) > 100:
        raise OperationError("publication_listing_incomplete")
    matches = [
        item
        for item in artifacts.get("artifacts", [])
        if item.get("name") == artifact_name(source["head_sha"], attempt)
    ]
    if len(matches) != 1:
        raise OperationError("unique_publication_record_required")
    artifact = matches[0]
    if (
        artifact.get("expired") is not False
        or not 0 < artifact.get("size_in_bytes", 0) <= 65536
        or artifact.get("workflow_run", {}).get("id") != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != source["head_sha"]
    ):
        raise OperationError("publication_artifact_unavailable")
    record = evidence.record(positive(artifact["id"]))
    validate_record(record, image, run_id, attempt)
    if record["commit"] != source["head_sha"]:
        raise OperationError("publication_commit_mismatch")
    descriptor, manifest = registry_manifest(image)
    validate_manifest(image, record["image_id"], descriptor, manifest)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        record = verify(args.image, args.run_id, args.attempt)
        if args.output:
            atomic_json(args.output, record)
        print(json.dumps({"verified": True, "image": record["image"], "commit": record["commit"]}))
        return 0
    except (OperationError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        code = str(error) if isinstance(error, OperationError) else "image_verification_failed"
        print(json.dumps({"verified": False, "issues": [code]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
