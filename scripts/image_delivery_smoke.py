"""Real save/load/push/readback using a loopback registry, never GHCR or the VPS."""

# ruff: noqa: S101 -- executable integration assertions

import argparse
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from deploy.common import run
from deploy.image_provenance import IMAGE_REPOSITORY, registry_manifest, validate_manifest
from scripts.image_candidate import export, inspect_candidate, load

REGISTRY = "registry:3@sha256:82f6ff4a7f982960c8aa51617fea3aabc485df6e55cce80d22deb1de36f1bc3c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("work/image-delivery-smoke.json"))
    args = parser.parse_args()
    original = json.loads(run(["docker", "image", "inspect", "muqola:local"]))[0]
    commit = original["Config"]["Labels"]["org.opencontainers.image.revision"]
    image_id = original["Id"]
    # Local synthetic identity, not an assertion of a real publication. CI uses its real context.
    if "GITHUB_RUN_ID" not in os.environ:
        os.environ.update(
            GITHUB_REPOSITORY="tlamart/muqola",
            GITHUB_EVENT_NAME="push",
            GITHUB_REF="refs/heads/main",
            GITHUB_SHA=commit,
            GITHUB_RUN_ID="1",
            GITHUB_RUN_ATTEMPT="1",
        )
    name = "muqola-registry-synthetic-" + uuid.uuid4().hex[:10]
    volume = name + "_data"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # Retain this volume even on failure; no prune or volume destruction.
    run(["docker", "volume", "create", volume])
    (args.report.parent / (name + "-volumes.json")).write_text(json.dumps([volume]))
    started = False
    try:
        with tempfile.TemporaryDirectory(prefix="muqola-image-") as directory:
            location = Path(directory)
            candidate = export(location, image_id)
            loaded = load(location, image_id, publishing=False)
            assert candidate == loaded
            inspect_candidate(image_id, commit)
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--publish",
                    "127.0.0.1::5000",
                    "--mount",
                    f"type=volume,source={volume},target=/var/lib/registry",
                    REGISTRY,
                ]
            )
            started = True
            network = json.loads(run(["docker", "inspect", name]))[0]["NetworkSettings"]
            port = network["Ports"]["5000/tcp"][0]["HostPort"]
            opener = build_opener(ProxyHandler({}))
            for attempt in range(30):
                try:
                    with opener.open(f"http://127.0.0.1:{port}/v2/", timeout=2) as response:  # noqa: S310 -- synthetic loopback registry only
                        assert response.status == 200
                    break
                except OSError:
                    if attempt == 29:
                        raise
                    time.sleep(0.2)
            tag = f"127.0.0.1:{port}/muqola-synthetic:{commit}"
            run(["docker", "image", "tag", image_id, tag])
            run(["docker", "image", "push", tag])
            published = json.loads(run(["docker", "image", "inspect", tag]))[0]
            reference = next(
                v for v in published["RepoDigests"] if v.startswith(f"127.0.0.1:{port}/")
            )
            descriptor, manifest = registry_manifest(reference)
            # Apply the same content checks to the loopback manifest. This is not GHCR evidence.
            validate_manifest(
                IMAGE_REPOSITORY + "@" + reference.split("@")[1], image_id, descriptor, manifest
            )
            assert published["Id"] == image_id
            report = {
                "image_delivery_smoke": "passed",
                "exact_save_load": True,
                "registry_manifest_readback": True,
                "configuration_digest_preserved": True,
                "archive_sha256": candidate["archive_sha256"],
                "volumes_preserved": True,
                "ghcr_publication_validated": False,
            }
            args.report.write_text(json.dumps(report))
            print(json.dumps(report))
    finally:
        if started:
            run(["docker", "stop", name])
            run(["docker", "container", "rm", name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
