import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from envskill.cli import main


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


if __name__ == "__main__":
    unittest.main()
