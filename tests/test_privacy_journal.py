import copy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from deploy.common import OperationError
from deploy.journal import apply_logging, error_log_command


def test_logging_is_opt_in_and_does_not_mutate_other_compose_settings() -> None:
    model: dict[str, Any] = {
        "services": {
            "web": {"image": "synthetic", "logging": {"driver": "json-file"}},
            "db": {"volumes": ["persistent-data"], "logging": {"driver": "json-file"}},
        }
    }
    before = copy.deepcopy(model)
    apply_logging(model, {})
    assert model == before
    with patch.object(Path, "is_socket", return_value=True):
        apply_logging(
            model,
            {
                "environment": "production",
                "journal_namespace": "muqola-production",
                "project": "muqola-prod",
            },
        )
    for name, service in model["services"].items():
        logging = service.pop("logging")
        assert logging["driver"] == "syslog"
        assert logging["options"]["cache-disabled"] == "true"
        assert logging["options"]["tag"] == "muqola-prod-" + name
        assert (
            logging["options"]["syslog-address"]
            == "unixgram:///run/systemd/journal.muqola-production/dev-log"
        )
        before["services"][name].pop("logging")
    assert model == before


@pytest.mark.parametrize("namespace", ["default", "../system", "muqola-staging", "arbitrary"])
def test_only_environment_specific_namespace_is_allowed(namespace: str) -> None:
    with pytest.raises(OperationError, match="isolated_journal_namespace_required"):
        apply_logging(
            {"services": {}}, {"journal_namespace": namespace, "environment": "production"}
        )


def test_absent_host_setup_blocks_plan_instead_of_silently_losing_logs() -> None:
    with (
        patch.object(Path, "is_socket", return_value=False),
        pytest.raises(OperationError, match="journal_namespace_socket_required"),
    ):
        apply_logging({"services": {}}, {"journal_namespace": "muqola-production"})


def test_monitor_reads_only_its_namespaced_service_logs() -> None:
    cmd = error_log_command({"journal_namespace": "muqola-production", "project": "muqola-prod"})
    assert "--namespace=muqola-production" in cmd
    assert "SYSLOG_IDENTIFIER=muqola-prod-web" in cmd
    assert "SYSLOG_IDENTIFIER=muqola-prod-worker" in cmd
    assert "SYSLOG_IDENTIFIER=caddy" not in cmd


def test_namespace_retention_has_time_bound_and_does_not_touch_host_journal() -> None:
    config = Path("deploy/systemd/journald-muqola.conf.example").read_text()
    assert "MaxRetentionSec=6day" in config and "MaxFileSec=1h" in config
    service = Path("deploy/systemd/muqola-journal-retention@.service").read_text()
    assert "--namespace=muqola-%i" in service and "--vacuum-time=6days" in service
    assert "truncate" not in service and "docker.sock" not in service
