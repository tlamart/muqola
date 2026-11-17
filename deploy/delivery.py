"""Trusted runner transport; no VPS connection except explicit manual workflow execution."""

import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from deploy.common import OperationError, run
from deploy.image_provenance import SHA, GitHubEvidence, verify
from deploy.release import ASSETS, SHA256, digest


def ssh_options(directory: Path) -> tuple[str, list[str]]:
    host, user = os.environ["VPS_HOST"], os.environ["VPS_USER"]
    if (
        not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", host)
        or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user)
        or user == "root"
    ):
        raise OperationError("invalid_ssh_target")
    key, known = directory / "key", directory / "known_hosts"
    key.write_text(os.environ["VPS_SSH_KEY"] + "\n")
    contents = os.environ["SSH_KNOWN_HOSTS"]
    if any(character in contents for character in ("*", "?", "@cert-authority")):
        raise OperationError("explicit_known_host_keys_required")
    known.write_text(contents + "\n")
    key.chmod(0o600)
    known.chmod(0o600)
    run(["ssh-keygen", "-F", host, "-f", str(known)])
    options = [
        "-F",
        "/dev/null",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(known),
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=1",
    ]
    return user + "@" + host, options


def approved_plan(environment: str, run_id: int, expected_hash: str) -> dict[str, Any]:
    from deploy.image_provenance import positive

    evidence = GitHubEvidence()
    run_id = positive(run_id)
    source = evidence.get(f"actions/runs/{run_id}")
    if (
        source.get("id") != run_id
        or source.get("repository", {}).get("full_name") != "tlamart/muqola"
        or source.get("event") != "workflow_dispatch"
        or source.get("head_branch") != "main"
        or source.get("path") != ".github/workflows/deploy.yml"
        or source.get("conclusion") != "success"
        or source.get("status") != "completed"
        or source.get("head_repository", {}).get("full_name") != "tlamart/muqola"
    ):
        raise OperationError("successful_manual_plan_run_required")
    attempt = positive(source.get("run_attempt"))
    items = evidence.get(f"actions/runs/{run_id}/artifacts?per_page=100")
    matches = [a for a in items["artifacts"] if a["name"] == f"muqola-plan-{environment}-{attempt}"]
    if items["total_count"] > 100 or len(matches) != 1 or matches[0]["expired"]:
        raise OperationError("plan_artifact_unavailable")
    # Same bounded ZIP reader, with a fixed, explicitly expected filename.
    import io

    artifact = matches[0]
    if artifact["size_in_bytes"] > 65536 or artifact["workflow_run"]["id"] != run_id:
        raise OperationError("invalid_plan_artifact")
    archive = run(
        [
            "gh",
            "api",
            "--method",
            "GET",
            f"repos/tlamart/muqola/actions/artifacts/{positive(artifact['id'])}/zip",
        ]
    )
    if len(archive) > 65536:
        raise OperationError("plan_archive_too_large")
    with zipfile.ZipFile(io.BytesIO(archive)) as contents:
        if contents.namelist() != ["plan.json"] or contents.getinfo("plan.json").file_size > 32768:
            raise OperationError("invalid_plan_files")
        value = json.loads(contents.read("plan.json"))
    if (
        value["hash"] != expected_hash
        or digest(value["plan"]) != expected_hash
        or value["plan"]["environment"] != environment
    ):
        raise OperationError("approved_plan_mismatch")
    return value  # type: ignore[no-any-return]


def remote_request(arguments: list[str], request: Any) -> dict[str, Any]:
    try:
        result = subprocess.run(  # noqa: S603 -- fixed command and validated target
            arguments, stdin=request, capture_output=True, check=False, timeout=1800
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperationError("ssh_interrupted_inspect_state_before_replanning") from error
    if result.returncode:
        try:
            issue = json.loads(result.stdout)["issues"][0]
            if not isinstance(issue, str) or not re.fullmatch(r"[a-z_]{1,120}", issue):
                raise ValueError
        except (ValueError, KeyError, TypeError, IndexError):
            issue = "identity_or_transport_failed"
        raise OperationError("host_" + issue)
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise OperationError("invalid_controller_response")
    return value


def deliver(args: argparse.Namespace) -> dict[str, Any]:
    if (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_REPOSITORY") != "tlamart/muqola"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
    ):
        raise OperationError("manual_main_workflow_only")
    if (
        args.environment not in {"staging", "production"}
        or args.action not in {"plan", "apply"}
        or args.kind not in {"deploy", "rollback"}
    ):
        raise OperationError("explicit_delivery_target_required")
    publication = verify(args.image, args.publication_run, args.publication_attempt)
    if args.action == "apply":
        if not SHA256.fullmatch(args.plan_hash):
            raise OperationError("explicit_plan_hash_required")
        plan = approved_plan(args.environment, args.plan_run, args.plan_hash)["plan"]
        if plan["image"] != args.image or plan["kind"] != args.kind:
            raise OperationError("plan_target_mismatch")
    commit = publication["commit"]
    if not SHA.fullmatch(commit):
        raise OperationError("invalid_release_commit")
    with tempfile.TemporaryDirectory(prefix="muqola-delivery-") as temp:
        directory = Path(temp)
        destination, options = ssh_options(directory)
        prefix = ["ssh", "-T", *options, destination]
        remote = f"/var/lib/muqola/{args.environment}/cd/incoming/{commit}"
        run([*prefix, "mkdir -p " + remote + "/deploy/postgres"])
        manifest = {}
        for name in ASSETS:
            entry = json.loads(
                run(
                    [
                        "gh",
                        "api",
                        "--method",
                        "GET",
                        f"repos/tlamart/muqola/contents/{name}?ref={commit}",
                    ]
                )
            )
            if (
                entry.get("type") != "file"
                or entry.get("path") != name
                or entry.get("encoding") != "base64"
                or not 0 < entry.get("size", 0) <= 65536
            ):
                raise OperationError("versioned_release_asset_required")
            content = base64.b64decode("".join(entry["content"].split()), validate=True)
            if len(content) != entry["size"]:
                raise OperationError("release_asset_size_mismatch")
            local = directory / name
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
            import hashlib

            manifest[name] = hashlib.sha256(content).hexdigest()
            run(["scp", "-B", *options, str(local), destination + ":" + remote + "/" + name])
        payload = {
            "protocol": 1,
            "publication": publication,
            "assets": manifest,
            "kind": args.kind,
            "registry_user": os.environ["GITHUB_ACTOR"],
            "registry_token": os.environ["GH_TOKEN"],
        }
        with tempfile.TemporaryFile() as request:
            request.write(json.dumps(payload).encode())
            request.seek(0)
            command = (
                "cd /opt/muqola-controller && python3 -m deploy.release "
                f"{args.environment} {args.action}"
            )
            if args.action == "apply":
                command += " --approved " + args.plan_hash
            result = remote_request([*prefix, command], request)
        if args.action == "plan":
            if (
                result["hash"] != digest(result["plan"])
                or result["plan"].get("environment") != args.environment
                or result["plan"].get("image") != args.image
                or result["plan"].get("kind") != args.kind
            ):
                raise OperationError("remote_plan_integrity_failed")
            Path("work").mkdir(exist_ok=True)
            Path("work/plan.json").write_text(json.dumps(result, indent=2))
        elif result.get("phase") != "succeeded" or result.get("image") != args.image:
            raise OperationError("release_success_not_confirmed")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("staging", "production"))
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--kind", choices=("deploy", "rollback"), required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--publication-run", type=int, required=True)
    parser.add_argument("--publication-attempt", type=int, required=True)
    parser.add_argument("--plan-run", type=int, default=0)
    parser.add_argument("--plan-hash", default="")
    args = parser.parse_args()
    try:
        print(json.dumps(deliver(args)))
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as error:
        code = str(error) if isinstance(error, OperationError) else "delivery_refused_or_failed"
        print(json.dumps({"issues": [code]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
