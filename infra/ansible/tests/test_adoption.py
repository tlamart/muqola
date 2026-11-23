"""Real Ansible against temporary synthetic files; no SSH, sudo or Docker access."""

import getpass
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-only-do-not-log-ansible-fixture"  # noqa: S105 — synthetic canary
DIRECTORIES = (
    "etc/muqola",
    "etc/muqola/secrets",
    "etc/muqola/staging",
    "etc/muqola/staging/secrets",
    "var/lib/muqola",
    "var/lib/muqola/production",
    "var/lib/muqola/production/cd",
    "var/lib/muqola/staging",
    "var/lib/muqola/staging/cd",
)


class AdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = tempfile.TemporaryDirectory(prefix="muqola-ansible-test-")
        self.addCleanup(self.fixture.cleanup)
        self.control = tempfile.TemporaryDirectory(prefix="muqola-ansible-control-")
        self.addCleanup(self.control.cleanup)
        self.root = Path(self.fixture.name)
        self.control_root = Path(self.control.name)
        for directory in (*DIRECTORIES, "opt/caddy", "opt/muqola-controller/deploy"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        files = {
            "etc/muqola/secrets/db_app_password": SECRET,
            "etc/muqola/staging/secrets/django_key": SECRET,
            "etc/muqola/production.env": f"SYNTHETIC_SECRET={SECRET}\n",
            "etc/muqola/staging/staging.env": f"SYNTHETIC_SECRET={SECRET}\n",
            "etc/muqola/release.json": json.dumps({"synthetic_secret": SECRET}),
            "var/lib/muqola/production/cd/state.json": '{"current":"synthetic-digest"}',
            "var/lib/muqola/production/cd/models/fixture/compose.json": "{}",
            "var/lib/muqola/staging/cd/state.json": '{"current":"another-digest"}',
            "var/lib/muqola/cd.lock": "",
            "opt/muqola-controller/deploy/release.py": "# synthetic installed version\n",
            "opt/caddy/Caddyfile": f"# existing routes + synthetic auth {SECRET}\n",
            "opt/caddy/compose.yaml": "# existing shared Caddy\n",
            "var/lib/docker/volumes/synthetic-db/_data/fixture": "preserve database",
            "etc/systemd/system/muqola-production-backup.timer": "# existing timer\n",
            "etc/systemd/system/muqola-production-backup-notify@.service": SECRET,
        }
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o444 if "/secrets/" in name else 0o600)
        (self.root / "var/lib/muqola/production/cd/active").symlink_to("models/fixture")
        for directory in DIRECTORIES:
            (self.root / directory).chmod(0o755)
        self.inventory = self.control_root / "inventory.json"
        self.variables: dict[str, Any] = {
            "ansible_connection": "local",
            "ansible_become": False,
            "ansible_python_interpreter": os.environ.get("MUQOLA_TEST_PYTHON", sys.executable),
            "ansible_remote_tmp": str(self.control_root / "remote"),
            "muqola_host_fixture_root": str(self.root),
            "muqola_host_deploy_user": getpass.getuser(),
        }
        self.environment = dict(
            os.environ,
            ANSIBLE_CONFIG=str(ROOT / "ansible.cfg"),
            ANSIBLE_HOME=str(self.control_root / "home"),
            ANSIBLE_LOCAL_TEMP=str(self.control_root / "local"),
            ANSIBLE_NOCOLOR="1",
            ANSIBLE_ROLES_PATH=str(ROOT / "roles"),
        )

    def snapshot(self) -> dict[str, tuple[Any, ...]]:
        result: dict[str, tuple[Any, ...]] = {}
        for path in self.root.rglob("*"):
            metadata = path.lstat()
            content = (
                os.readlink(path)
                if path.is_symlink()
                else path.read_bytes()
                if path.is_file()
                else None
            )
            result[str(path.relative_to(self.root))] = (
                stat.S_IMODE(metadata.st_mode),
                metadata.st_uid,
                metadata.st_gid,
                content,
            )
        return result

    def playbook(
        self,
        name: str,
        *,
        approved: bool = False,
        check: bool = False,
        expected_success: bool = True,
    ) -> str:
        self.inventory.write_text(
            json.dumps({"muqola_vps": {"hosts": {"synthetic": self.variables}}})
        )
        executable = shutil.which("ansible-playbook")
        self.assertIsNotNone(executable, "Run with uv run --frozen in infra/ansible")
        command = [
            str(executable),
            "-i",
            str(self.inventory),
            str(ROOT / "playbooks" / f"{name}.yml"),
            "-e",
            json.dumps({"muqola_host_approved": approved}),
        ]
        if check:
            command.extend(["--check", "--diff"])
        result = subprocess.run(  # noqa: S603 — fixed playbook and synthetic local inventory
            command,
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertNotIn(SECRET, output, "A private fixture value leaked into Ansible output")
        if expected_success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def test_audit_and_check_are_read_only_then_adoption_is_idempotent(self) -> None:
        before = self.snapshot()
        audit = self.playbook("audit")
        self.assertRegex(audit, r"changed=0\b")
        self.assertEqual(self.snapshot(), before)
        preview = self.playbook("adopt", check=True)
        self.assertRegex(preview, r"changed=[1-9]\d*\b")
        self.assertEqual(self.snapshot(), before)
        self.playbook("adopt", approved=True)
        after = self.snapshot()
        expected = dict(before)
        for directory in DIRECTORIES:
            expected[directory] = (0o700, *before[directory][1:])
        self.assertEqual(after, expected, "Only the listed directory permissions may change")
        repeat = self.playbook("adopt", approved=True)
        self.assertRegex(repeat, r"changed=0\b")
        self.assertEqual(self.snapshot(), after)

    def test_adoption_requires_explicit_approval(self) -> None:
        before = self.snapshot()
        output = self.playbook("adopt", expected_success=False)
        self.assertIn("adoption non approuvée", output)
        self.assertEqual(self.snapshot(), before)

    def test_missing_installation_is_not_initialized(self) -> None:
        (self.root / "etc/muqola/staging/secrets/django_key").unlink()
        (self.root / "etc/muqola/staging/secrets").rmdir()
        before = self.snapshot()
        output = self.playbook("adopt", approved=True, expected_success=False)
        self.assertIn("Installation incomplète", output)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_directory_is_refused_before_any_change(self) -> None:
        path = self.root / "etc/muqola/secrets"
        destination = self.root / "synthetic-other-secrets"
        path.rename(destination)
        path.symlink_to(destination)
        before = self.snapshot()
        output = self.playbook("adopt", approved=True, expected_success=False)
        self.assertIn("répertoire redirigé", output)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_parent_is_refused(self) -> None:
        path = self.root / "var/lib"
        destination = self.root / "synthetic-other-lib"
        path.rename(destination)
        path.symlink_to(destination)
        before = self.snapshot()
        output = self.playbook("adopt", approved=True, expected_success=False)
        self.assertIn("Parent absent ou lien symbolique", output)
        self.assertEqual(self.snapshot(), before)

    def test_local_mode_cannot_target_the_real_host(self) -> None:
        before = self.snapshot()
        for root in ("", "/", "/tmp", "/tmp/muqola-ansible-test-x/../../etc"):  # noqa: S108
            with self.subTest(root=root):
                self.variables["muqola_host_fixture_root"] = root
                self.playbook("adopt", approved=True, expected_success=False)
                self.assertEqual(self.snapshot(), before)

    def test_local_fixture_cannot_use_privilege_escalation(self) -> None:
        before = self.snapshot()
        self.variables["ansible_become"] = True
        self.playbook("adopt", approved=True, expected_success=False)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_fixture_root_is_refused(self) -> None:
        before = self.snapshot()
        destination = self.control_root / "original-fixture"
        self.root.rename(destination)
        self.root.symlink_to(destination, target_is_directory=True)
        try:
            output = self.playbook("adopt", approved=True, expected_success=False)
            self.assertIn("Racine synthétique absente ou redirigée", output)
            self.assertEqual(self.snapshot(), before)
        finally:
            self.root.unlink()
            destination.rename(self.root)

    def test_no_default_live_inventory_or_runtime_dependency(self) -> None:
        config = (ROOT / "ansible.cfg").read_text()
        self.assertIn("host_key_checking = True", config)
        self.assertIn("StrictHostKeyChecking=yes", config)
        example = (ROOT / "inventory.example.yml").read_text()
        self.assertIn("vps.example.invalid", example)
        repo = ROOT.parents[1]
        self.assertIn("infra/ansible", (repo / ".dockerignore").read_text())
        self.assertNotIn("ansible", (repo / "requirements.txt").read_text().lower())
        workflow = (repo / ".github/workflows/ansible.yml").read_text()
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("workflow_dispatch", workflow)
        self.assertIn("contents: read", workflow)
        self.assertFalse(re.search(r"^\s+environment:", workflow, re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
