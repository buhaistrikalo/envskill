import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from envskill.cli import main
from envskill.setup import bundled_skill
from envskill.store import load


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "secrets.env"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *arguments, stdin=""):
        output = io.StringIO()
        error = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(stdin)),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(error),
        ):
            code = main(["--file", str(self.path), *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_set_and_list_never_print_value(self):
        code, output, error = self.call("set", "TOKEN", "--stdin", stdin="super-secret\n")
        self.assertEqual((code, error), (0, ""))
        self.assertNotIn("super-secret", output)
        code, output, _ = self.call("list")
        self.assertEqual(code, 0)
        self.assertEqual(output, "TOKEN\n")
        self.assertNotIn("super-secret", output)

    def test_has_returns_one_when_missing(self):
        code, output, _ = self.call("has", "MISSING")
        self.assertEqual(code, 1)
        self.assertEqual(output, "MISSING: missing\n")

    def test_doctor_json_missing_store_is_read_only(self):
        targets = {
            name: Path(self.temp.name) / f"{name}-skills"
            for name in ("codex", "claude", "hermes")
        }
        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "all", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(report["schema_version"], 1)
        self.assertFalse(report["store"]["exists"])
        self.assertEqual(report["store"]["type"], "missing")
        self.assertFalse(self.path.exists())
        self.assertTrue(all(not (parent / "envskill").exists() for parent in targets.values()))

    @unittest.skipUnless(os.name == "posix", "POSIX permissions")
    def test_doctor_json_reports_insecure_store_without_values(self):
        self.path.write_text('TOKEN="doctor-secret"\n', encoding="utf-8")
        self.path.chmod(0o644)
        target = Path(self.temp.name) / "codex-skills"
        target.mkdir()
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}

        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "codex", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(report["store"]["mode"], "0644")
        self.assertTrue(report["store"]["parseable"])
        self.assertIn("insecure_mode", {item["code"] for item in report["problems"]})
        self.assertNotIn("doctor-secret", output)
        self.assertIn("envskill --file", report["problems"][0]["remediation"][0])

    @unittest.skipUnless(os.name == "posix", "symlink behavior is POSIX-specific")
    def test_doctor_does_not_follow_symlinked_store(self):
        real_store = Path(self.temp.name) / "real.env"
        real_store.write_text('TOKEN="doctor-secret"\n', encoding="utf-8")
        real_store.chmod(0o600)
        self.path.symlink_to(real_store)
        target = Path(self.temp.name) / "codex-skills"
        target.mkdir()
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}

        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "codex", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(report["store"]["type"], "symlink")
        self.assertIsNone(report["store"]["parseable"])
        self.assertEqual(real_store.read_text(encoding="utf-8"), 'TOKEN="doctor-secret"\n')
        self.assertNotIn("doctor-secret", output)

    def test_doctor_reports_missing_skill_without_creating_it(self):
        self.call("set", "TOKEN", "--stdin", stdin="doctor-secret")
        target = Path(self.temp.name) / "codex-skills"
        target.mkdir()
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}

        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "codex", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(report["agents"][0]["status"], "missing")
        self.assertFalse((target / "envskill").exists())
        self.assertNotIn("doctor-secret", output)

    def test_doctor_reports_conflicting_skill_without_mutating_it(self):
        self.call("set", "TOKEN", "--stdin", stdin="doctor-secret")
        target = Path(self.temp.name) / "codex-skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text("custom skill", encoding="utf-8")
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "codex", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (1, ""))
        self.assertEqual(report["agents"][0]["status"], "conflict")
        self.assertFalse(report["agents"][0]["bundled_copy_match"])
        self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill")
        conflict = next(item for item in report["problems"] if item["code"] == "conflict")
        self.assertIn("--force", conflict["remediation"][0])

    def test_doctor_checks_all_supported_targets(self):
        self.call("set", "TOKEN", "--stdin", stdin="doctor-secret")
        targets = {}
        for name in ("codex", "claude", "hermes"):
            parent = Path(self.temp.name) / f"{name}-skills"
            (parent / "envskill").mkdir(parents=True)
            (parent / "envskill" / "SKILL.md").write_text(
                bundled_skill().read_text(encoding="utf-8"), encoding="utf-8"
            )
            targets[name] = parent
        targets["universal"] = targets["codex"]

        with (
            patch("envskill.cli.TARGET_DIRS", targets),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor", "--agent", "all", "--json")

        report = json.loads(output)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(report["agent_selection"]["selected"], ["codex", "claude", "hermes"])
        self.assertEqual(
            [agent["status"] for agent in report["agents"]], ["match", "match", "match"]
        )
        self.assertEqual(report["store"]["mode"], "0600")
        self.assertNotIn("doctor-secret", output)

    def test_doctor_human_output_keeps_success_summary(self):
        self.call("set", "TOKEN", "--stdin", stdin="doctor-secret")
        with (
            patch("envskill.cli.detect_agents", return_value=[]),
            patch("envskill.doctor.shutil.which", return_value="/usr/bin/envskill"),
        ):
            code, output, error = self.call("doctor")

        self.assertEqual((code, error), (0, ""))
        self.assertIn("OK: store=", output)
        self.assertIn("permissions=private; cli=available", output)
        self.assertNotIn("doctor-secret", output)

    def test_run_injects_only_selected_names(self):
        self.call("set", "ONE", "--stdin", stdin="first")
        self.call("set", "TWO", "--stdin", stdin="second")
        command = [
            sys.executable,
            "-c",
            "import os,sys; "
            "sys.exit(0 if os.getenv('ONE') == 'first' "
            "and 'TWO' not in os.environ "
            "and 'OUTSIDE_SECRET' not in os.environ "
            "and 'LC_API_KEY' not in os.environ else 1)",
        ]
        parent_environment = os.environ.copy()
        parent_environment["TWO"] = "already-leaked-from-parent"
        parent_environment["OUTSIDE_SECRET"] = "not-managed-by-envskill"
        parent_environment["LC_API_KEY"] = "must-not-leak"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "envskill.cli",
                "--file",
                str(self.path),
                "run",
                "--only",
                "ONE",
                "--",
                *command,
            ],
            check=False,
            env=parent_environment,
        )
        self.assertEqual(result.returncode, 0)

    def test_explicit_inherit_preserves_named_parent_variable(self):
        self.call("set", "TOKEN", "--stdin", stdin="secret")
        environment = os.environ.copy()
        environment["CUSTOM_SOCKET"] = "/tmp/example.sock"
        command = [
            sys.executable,
            "-c",
            "import os,sys; "
            "sys.exit(0 if os.getenv('CUSTOM_SOCKET') == '/tmp/example.sock' else 1)",
        ]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "envskill.cli",
                "--file",
                str(self.path),
                "run",
                "--only",
                "TOKEN",
                "--inherit",
                "CUSTOM_SOCKET",
                "--",
                *command,
            ],
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0)

    def test_install_skill_to_custom_directory(self):
        parent = Path(self.temp.name) / "skills"
        code, output, error = self.call("install-skill", "--dir", str(parent))
        self.assertEqual((code, error), (0, ""))
        skill = parent / "envskill" / "SKILL.md"
        self.assertTrue(skill.exists())
        self.assertIn("name: envskill", skill.read_text())
        self.assertIn(str(skill), output)

    @unittest.skipUnless(os.name == "posix", "symlink behavior is POSIX-specific")
    def test_install_skill_force_rejects_symlink_and_regular_file_destinations(self):
        parent = Path(self.temp.name) / "skills"
        parent.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        destination = parent / "envskill"
        destination.symlink_to(outside, target_is_directory=True)
        code, _, error = self.call("install-skill", "--dir", str(parent), "--force")
        self.assertEqual(code, 2)
        self.assertIn("real directory", error)
        self.assertFalse((outside / "SKILL.md").exists())

        destination.unlink()
        destination.write_text("not a directory", encoding="utf-8")
        code, _, error = self.call("install-skill", "--dir", str(parent), "--force")
        self.assertEqual(code, 2)
        self.assertIn("real directory", error)
        self.assertNotIn("Traceback", error)

        destination.unlink()
        destination.mkdir()
        target = destination / "SKILL.md"
        outside_file = outside / "do-not-overwrite.md"
        outside_file.write_text("safe", encoding="utf-8")
        target.symlink_to(outside_file)
        code, _, error = self.call("install-skill", "--dir", str(parent), "--force")
        self.assertEqual(code, 2)
        self.assertIn("non-symlink", error)
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "safe")

        unsafe_parent = Path(self.temp.name) / "unsafe-skills"
        unsafe_parent.mkdir(mode=0o777)
        unsafe_parent.chmod(0o777)
        code, _, error = self.call("install-skill", "--dir", str(unsafe_parent))
        self.assertEqual(code, 2)
        self.assertIn("writable by another user", error)

    def test_import_env_hides_values_and_preserves_existing_by_default(self):
        source = Path(self.temp.name) / "source.env"
        source.write_text('TOKEN="new-secret"\nSECOND="another-secret"\n', encoding="utf-8")
        self.call("set", "TOKEN", "--stdin", stdin="existing-secret")
        code, output, error = self.call("import-env", "--from", str(source))
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Imported 1 variable(s); skipped 1", output)
        self.assertNotIn("new-secret", output)
        self.assertNotIn("another-secret", output)
        self.assertEqual(self.path.read_text().count("TOKEN="), 1)
        code, output, _ = self.call("list")
        self.assertEqual((code, output), (0, "SECOND\nTOKEN\n"))

    def test_setup_initializes_store_installs_skill_and_runs_doctor(self):
        target = Path(self.temp.name) / "skills"
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}
        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex")

        self.assertEqual((code, error), (0, ""))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertTrue((target / "envskill" / "SKILL.md").is_file())
        self.assertIn("Store created:", output)
        self.assertIn("Skill installed for codex:", output)
        self.assertIn("Doctor: OK", output)

    def test_setup_import_preserves_existing_names_and_hides_values(self):
        source = Path(self.temp.name) / "source.env"
        source.write_text(
            'EXISTING="replacement-placeholder"\nNEW="new-placeholder"\n', encoding="utf-8"
        )
        self.call("set", "EXISTING", "--stdin", stdin="existing-placeholder")
        target = Path(self.temp.name) / "skills"
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call(
                "setup", "--agent", "codex", "--import", str(source)
            )

        self.assertEqual((code, error), (0, ""))
        self.assertIn("Imported 1 variable(s); kept 1", output)
        self.assertNotIn("placeholder", output)
        self.assertEqual(load(self.path)["EXISTING"], "existing-placeholder")
        self.assertEqual(load(self.path)["NEW"], "new-placeholder")

    def test_setup_is_idempotent_for_an_identical_skill(self):
        target = Path(self.temp.name) / "skills"
        targets = {"universal": target, "codex": target, "claude": target, "hermes": target}
        with patch("envskill.cli.TARGET_DIRS", targets):
            first = self.call("setup", "--agent", "codex")
            second = self.call("setup", "--agent", "codex")

        self.assertEqual(first[0:3:2], (0, ""))
        self.assertEqual(second[0], 0)
        self.assertEqual(second[2], "")
        self.assertIn("already installed for codex", second[1])

    @unittest.skipUnless(os.name == "posix", "skill permission behavior is POSIX-specific")
    def test_setup_rejects_insecure_existing_skill_before_mutating_store(self):
        target = Path(self.temp.name) / "skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text("custom skill", encoding="utf-8")
        skill.chmod(0o666)
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex")

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("SKILL.md", error)
        self.assertIn("writable by another user", error)
        self.assertFalse(self.path.exists())
        self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill")

    @unittest.skipUnless(os.name == "posix", "skill permission behavior is POSIX-specific")
    def test_setup_force_replaces_insecure_existing_skill(self):
        target = Path(self.temp.name) / "skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text("custom skill", encoding="utf-8")
        skill.chmod(0o666)
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex", "--force")

        self.assertEqual((code, error), (0, ""))
        self.assertIn("Skill updated for codex", output)
        self.assertIn("name: envskill", skill.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(skill.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "skill permission behavior is POSIX-specific")
    def test_setup_force_replaces_unreadable_existing_skill(self):
        target = Path(self.temp.name) / "skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text("custom skill", encoding="utf-8")
        skill.chmod(0o000)
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex", "--force")

        self.assertEqual((code, error), (0, ""))
        self.assertIn("Skill updated for codex", output)
        self.assertIn("name: envskill", skill.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(skill.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "directory permission behavior is POSIX-specific")
    def test_setup_preflights_all_targets_before_mutating_store(self):
        good = Path(self.temp.name) / "good-skills"
        bad = Path(self.temp.name) / "bad-skills"
        bad.mkdir()
        bad.chmod(0o777)
        targets = {
            "universal": good,
            "codex": good,
            "claude": bad,
            "hermes": good,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "all")

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("writable by another user", error)
        self.assertFalse(self.path.exists())
        self.assertFalse((good / "envskill" / "SKILL.md").exists())

    @unittest.skipUnless(os.name == "posix", "skill permission behavior is POSIX-specific")
    def test_setup_force_replaces_identical_insecure_existing_skill(self):
        target = Path(self.temp.name) / "skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text(bundled_skill().read_text(encoding="utf-8"), encoding="utf-8")
        skill.chmod(0o666)
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex", "--force")

        self.assertEqual((code, error), (0, ""))
        self.assertIn("Skill updated for codex", output)
        self.assertEqual(stat.S_IMODE(skill.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "directory permission behavior is POSIX-specific")
    def test_setup_rejects_nonwritable_target_before_mutating_store(self):
        parent = Path(self.temp.name) / "readonly-skills"
        parent.mkdir()
        parent.chmod(0o555)
        targets = {
            "universal": parent,
            "codex": parent,
            "claude": parent,
            "hermes": parent,
        }

        try:
            with patch("envskill.cli.TARGET_DIRS", targets):
                code, output, error = self.call("setup", "--agent", "codex")
        finally:
            parent.chmod(0o755)

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("not writable by the current user", error)
        self.assertFalse(self.path.exists())

    def test_setup_does_not_overwrite_existing_skill_without_force(self):
        target = Path(self.temp.name) / "skills" / "envskill"
        target.mkdir(parents=True)
        skill = target / "SKILL.md"
        skill.write_text("custom skill", encoding="utf-8")
        targets = {
            "universal": target.parent,
            "codex": target.parent,
            "claude": target.parent,
            "hermes": target.parent,
        }

        with patch("envskill.cli.TARGET_DIRS", targets):
            code, output, error = self.call("setup", "--agent", "codex")

        self.assertEqual((code, error), (0, ""))
        self.assertIn("not overwritten for codex", output)
        self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill")

    def test_setup_requires_explicit_import_flag_for_overwrite(self):
        code, _, error = self.call("setup", "--overwrite")
        self.assertEqual(code, 2)
        self.assertIn("--overwrite requires --import", error)


if __name__ == "__main__":
    unittest.main()
