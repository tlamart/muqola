"""Container-local probes; never expose worker/outbox metrics publicly."""

import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


def healthy(kind: str) -> bool:
    try:
        if kind == "worker":
            heartbeat = Path("/tmp/outbox-heartbeat")  # noqa: S108 — private container tmpfs
            age = time.time() - heartbeat.stat().st_mtime
            return 0 <= age <= 120
        if kind != "web":
            return False
        from urllib.parse import urlsplit

        host = urlsplit(os.environ["APP_BASE_URL"]).netloc
        request = Request(
            "http://127.0.0.1:8000/health/ready/",
            headers={"Host": host, "X-Forwarded-Proto": "https"},
        )
        with urlopen(request, timeout=4) as response:  # noqa: S310 — fixed container loopback
            return bool(response.status == 200)
    except (OSError, ValueError, KeyError):
        return False


if __name__ == "__main__":
    sys.exit(0 if len(sys.argv) == 2 and healthy(sys.argv[1]) else 1)
