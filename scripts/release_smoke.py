"""Exercise release.apply on the existing isolated staging witness, never a VPS.

Only admission/provenance and the local HTTPS routing are substituted; service
stop/start, schema inventories, readiness and the durable journal run for real.
No migration is pending in this fixture; migration failure paths have unit tests.
"""

# ruff: noqa: S101 -- executable integration assertions

import argparse
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from deploy import release
from deploy.common import OperationError, atomic_json, run, utcnow
from deploy.staging import require_local_docker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--compose-env", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--cacert", required=True)
    parser.add_argument("--netrc", required=True)
    args = parser.parse_args()
    model = json.loads(args.compose_file.read_text())
    origin = urlsplit(args.url)
    if (
        not model["name"].startswith("muqola-stage-synthetic-")
        or origin.hostname != "staging.muqola.tlam.art"
        or not origin.port
        or origin.port < 1024
    ):
        raise OperationError("synthetic_loopback_stack_required")
    require_local_docker()
    command = [
        "docker",
        "compose",
        "--env-file",
        args.compose_env,
        "-f",
        str(args.compose_file),
        "--profile",
        "staging",
    ]
    schema = release.snapshot(command)
    assert not schema["pending"]
    curl = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--noproxy",
        "*",
        "--cacert",
        args.cacert,
        "--netrc-file",
        args.netrc,
        "--resolve",
        f"{origin.hostname}:{origin.port}:127.0.0.1",
        args.url + "/health/ready/",
    ]

    def probe(_: object) -> None:
        run(curl)

    def count() -> bytes:
        return run(
            [
                *command,
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                '-Atc "SELECT count(*) FROM identity_user"',
            ]
        )

    before = count()
    cid = run([*command, "ps", "-q", "web"]).decode().strip()
    old_tag = model["name"] + ":cd-previous"
    # Test-only derivative: different configuration ID, same application code.
    # It is never published; bind mounts, DB and tmpfs data are not committed.
    run(["docker", "commit", "--change", "LABEL muqola.synthetic.cd=previous", cid, old_tag])

    def image_identity() -> str:
        container = run([*command, "ps", "-q", "web"]).decode().strip()
        return str(json.loads(run(["docker", "inspect", container]))[0]["Image"])

    with tempfile.TemporaryDirectory(prefix="muqola-cd-synthetic-", dir="work") as temp:
        root = Path(temp)
        previous_model = copy.deepcopy(model)
        for service in ("web", "worker", "migrate"):
            previous_model["services"][service]["image"] = old_tag
        previous_file = root / "previous-compose.json"
        atomic_json(previous_file, previous_model)
        old_command = [
            "docker",
            "compose",
            "--env-file",
            args.compose_env,
            "-f",
            str(previous_file),
            "--profile",
            "staging",
        ]
        run([*old_command, "up", "-d", "--no-deps", "--no-build", "--wait", "web", "worker"])
        old_identity = image_identity()
        initial = {"image": "synthetic-previous", "schema": schema["schema"], "commit": "a" * 40}
        state = {"current": initial}
        config = {"environment": "staging"}
        plan = {
            "environment": "staging",
            "kind": "deploy",
            "nonce": "f" * 32,
            "image": "synthetic-candidate",
            "schema": schema["schema"],
            "pending": [],
            "commit": "b" * 40,
            "compose_file": str(args.compose_file),
        }

        def save() -> str:
            key = release.digest(plan)
            atomic_json(
                root / "plans" / (key + ".json"), {"created_at": utcnow().isoformat(), "plan": plan}
            )
            return key

        # Harness-only adapters; no bypass flag is available in the host controller.
        with (
            patch.object(release, "make_plan", side_effect=lambda *a: copy.deepcopy(plan)),
            patch.object(
                release,
                "compose",
                side_effect=lambda runtime: [
                    "docker",
                    "compose",
                    "--env-file",
                    args.compose_env,
                    "-f",
                    runtime["compose_file"],
                    "--profile",
                    "staging",
                ],
            ),
            patch.object(release, "https_ready", side_effect=probe),
        ):
            key = save()
            release.apply(config, {"publication": {}}, root, state, key)
            assert count() == before
            candidate_identity = image_identity()
            assert candidate_identity != old_identity
            try:
                release.apply(config, {"publication": {}}, root, state, key)
            except OperationError as error:
                assert str(error) == "plan_already_consumed"
            else:
                raise AssertionError("Duplicate application was accepted")
            state = json.loads((root / "state.json").read_text())
            assert state["previous"] == initial
            plan.update(
                kind="rollback",
                image=initial["image"],
                commit=initial["commit"],
                compose_file=str(previous_file),
            )
            release.apply(config, {"publication": {}}, root, state, save())
            assert count() == before and image_identity() == old_identity
            state = json.loads((root / "state.json").read_text())
            previous = state["current"]
            plan.update(
                kind="deploy", image="synthetic-health-failure", compose_file=str(args.compose_file)
            )
            with patch.object(
                release, "https_ready", side_effect=OperationError("synthetic_health_failure")
            ):
                try:
                    release.apply(config, {"publication": {}}, root, state, save())
                except OperationError:
                    pass
                else:
                    raise AssertionError("Failed HTTPS was accepted")
            state = json.loads((root / "state.json").read_text())
            assert state["phase"] == "failed" and state["current"] == previous
            plan.update(image="synthetic-recovery")
            release.apply(config, {"publication": {}}, root, state, save())
            assert count() == before
    report = {
        "release_smoke": "passed",
        "real_service_cycles": True,
        "schema_preserved": True,
        "duplicate_refused": True,
        "image_only_rollback": True,
        "distinct_image_ids": True,
        "failed_health_and_replan": True,
        "volumes_preserved": True,
        "vps_validated": False,
        "migration_pending_in_fixture": False,
    }
    Path("work/release-smoke.json").write_text(json.dumps(report))
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
