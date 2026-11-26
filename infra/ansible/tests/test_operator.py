"""Exercise the real playbook locally; only the Docker executable is a fixture.

Transactional database behavior is tested by tests/test_operator_promotion.py.
This fixture records argv and supplies responses; it does not simulate accounts.
"""

import fcntl
import json
from pathlib import Path
from typing import Any

from test_adoption import LocalAnsibleFixture

EMAIL = "promotion-private@example.test"
REASON = "Habilitation confidentielle fictive ; $(touch forbidden-shell-expansion)"


class OperatorPlaybookTests(LocalAnsibleFixture):
    def setUp(self) -> None:
        super().setUp()
        for environment in ("staging", "production"):
            path = self.root / f"var/lib/muqola/{environment}/cd/release.lock"
            path.touch(mode=0o644)
        self.response: dict[str, Any] = {
            "status": "would_promote",
            "dry_run": True,
            "environment": "staging",
        }
        self.variables.update(
            muqola_operator_fixture_root=str(self.root),
            muqola_operator_environment="staging",
            muqola_operator_email=EMAIL,
            muqola_operator_confirm_email=EMAIL,
            muqola_operator_reason=REASON,
            muqola_operator_bootstrap=True,
        )
        self.record = self.root / "docker-argv.json"
        binary = self.root / "bin/docker"
        binary.parent.mkdir()
        binary.write_text(
            "#!/usr/bin/python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "os.umask(0o077)\n"
            "root = Path(__file__).resolve().parents[1]\n"
            "(root / 'docker-argv.json').write_text(json.dumps(sys.argv[1:]))\n"
            "response = json.loads((root / 'docker-response.json').read_text())\n"
            "print(response.get('stderr', ''), file=sys.stderr)\n"
            "print(response.get('raw', json.dumps(response['result'])))\n"
            "sys.exit(response.get('rc', 0))\n"
        )
        binary.chmod(0o700)

    def invoke(
        self,
        *,
        apply: bool = False,
        approved: bool = False,
        check: bool = False,
        success: bool = True,
        failure: dict[str, Any] | None = None,
    ) -> str:
        (self.root / "docker-response.json").write_text(
            json.dumps({"result": self.response, **(failure or {})})
        )
        output = self.playbook(
            "promote-operator",
            check=check,
            expected_success=success,
            extra={"muqola_operator_apply": apply, "muqola_operator_approved": approved},
        )
        for private_value in (EMAIL, REASON, "acteur-private@example.test"):
            self.assertNotIn(private_value, output)
        return output

    def arguments(self) -> list[str]:
        value: list[str] = json.loads(self.record.read_text())
        return value

    def test_default_is_read_only_and_preserves_exact_arguments(self) -> None:
        output = self.invoke()
        self.assertIn("would_promote", output)
        self.assertRegex(output, r"changed=0\b")
        arguments = self.arguments()
        self.assertEqual(
            arguments[:8],
            [
                "--host",
                "unix:///var/run/docker.sock",
                "exec",
                "muqola-staging-web-1",
                "python",
                "manage.py",
                "promote_operator",
                "--deployment-env",
            ],
        )
        self.assertEqual(arguments[8], "staging")
        self.assertEqual(arguments[arguments.index("--reason") + 1], REASON)
        self.assertEqual(arguments[arguments.index("--email") + 1], EMAIL)
        self.assertIn("--dry-run", arguments)
        self.assertIn("--bootstrap", arguments)
        self.assertIn("--if-needed", arguments)
        self.assertIn("--json", arguments)
        self.assertFalse((Path.cwd() / "forbidden-shell-expansion").exists())

    def test_check_keeps_dry_run_even_when_apply_is_selected(self) -> None:
        self.invoke(apply=True, check=True)
        self.assertIn("--dry-run", self.arguments())

    def test_apply_requires_approval_before_executing_any_command(self) -> None:
        self.invoke(apply=True, success=False)
        self.assertFalse(self.record.exists())

    def test_application_and_repeat_report_change_then_noop(self) -> None:
        self.response.update(status="promoted", dry_run=False)
        output = self.invoke(apply=True, approved=True)
        self.assertRegex(output, r"changed=1\b")
        self.assertNotIn("--dry-run", self.arguments())
        self.response["status"] = "unchanged"
        output = self.invoke(apply=True, approved=True)
        self.assertRegex(output, r"changed=0\b")

    def test_production_target_and_existing_actor_are_explicit(self) -> None:
        self.variables.update(
            muqola_operator_environment="production",
            muqola_operator_bootstrap=False,
            muqola_operator_actor="acteur-private@example.test",
        )
        self.response["environment"] = "production"
        self.invoke()
        arguments = self.arguments()
        self.assertEqual(arguments[3], "muqola-prod-web-1")
        self.assertEqual(arguments[8], "production")
        self.assertNotIn("--bootstrap", arguments)
        self.assertEqual(
            arguments[arguments.index("--operator") + 1], "acteur-private@example.test"
        )

    def test_busy_cd_lock_prevents_docker_execution(self) -> None:
        for name in ("cd.lock", "staging/cd/release.lock"):
            with self.subTest(lock=name), (self.root / "var/lib/muqola" / name).open("rb") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                output = self.invoke(success=False)
                self.assertIn("code 75", output)
                self.assertFalse(self.record.exists())

    def test_invalid_parameters_fail_without_calling_docker(self) -> None:
        cases = (
            {"muqola_operator_environment": ""},
            {"muqola_operator_environment": "development"},
            {"muqola_operator_confirm_email": "other@example.test"},
            {"muqola_operator_reason": ""},
            {"muqola_operator_actor": "acteur-private@example.test"},
            {"muqola_operator_bootstrap": False},
            {"muqola_operator_fixture_root": ""},
            {"ansible_become": True},
        )
        for changes in cases:
            with self.subTest(changes=tuple(changes)):
                original = dict(self.variables)
                self.variables.update(changes)
                self.invoke(success=False)
                self.variables = original
                self.assertFalse(self.record.exists())

    def test_errors_and_unexpected_responses_do_not_publish_private_output(self) -> None:
        self.invoke(success=False, failure={"rc": 2, "stderr": EMAIL + REASON})
        self.invoke(success=False, failure={"raw": "private invalid output " + EMAIL})
        self.response["environment"] = "production"
        self.invoke(success=False)

    def test_missing_or_redirected_lock_is_not_created_or_followed(self) -> None:
        lock = self.root / "var/lib/muqola/staging/cd/release.lock"
        lock.unlink()
        self.invoke(success=False)
        self.assertFalse(lock.exists())
        lock.symlink_to(self.root / "var/lib/muqola/cd.lock")
        self.invoke(success=False)
        self.assertTrue(lock.is_symlink())
        self.assertFalse(self.record.exists())

    def test_writable_group_or_other_lock_is_refused_without_repair(self) -> None:
        for name in ("cd.lock", "staging/cd/release.lock"):
            lock = self.root / "var/lib/muqola" / name
            for mode in (0o664, 0o606):
                with self.subTest(lock=name, mode=mode):
                    lock.chmod(mode)
                    self.invoke(success=False)
                    self.assertEqual(lock.stat().st_mode & 0o777, mode)
                    self.assertFalse(self.record.exists())
            lock.chmod(0o600)

    def test_explicit_mode_repair_preserves_busy_lock_and_then_allows_preview(self) -> None:
        lock = self.root / "var/lib/muqola/staging/cd/release.lock"
        lock.chmod(0o664)
        before = lock.stat()
        with lock.open("rb") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock.chmod(0o600)
            after = lock.stat()
            self.assertEqual(
                (before.st_dev, before.st_ino, before.st_uid, before.st_gid),
                (after.st_dev, after.st_ino, after.st_uid, after.st_gid),
            )
            output = self.invoke(success=False)
            self.assertIn("code 75", output)
            self.assertFalse(self.record.exists())
        output = self.invoke()
        self.assertIn("would_promote", output)
        self.assertIn("--dry-run", self.arguments())
