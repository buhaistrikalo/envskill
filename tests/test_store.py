import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from envskill.store import (
    StoreError,
    default_path,
    initialize,
    load,
    set_value,
    unset_value,
    validate_store,
)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "secrets.env"

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_special_values(self):
        values = {
            "PLAIN": "hello",
            "SPACES": "hello world # still secret",
            "QUOTES": "both ' and \" quotes",
            "MULTILINE": "first\nsecond",
            "UNICODE_LINES": "first\u0085second\u2028third\u2029fourth",
            "UNICODE": "секрет",
        }
        for name, value in values.items():
            set_value(self.path, name, value)
        self.assertEqual(load(self.path), values)

    def test_set_replaces_duplicates(self):
        self.path.write_text("TOKEN=old\nTOKEN=older\n", encoding="utf-8")
        self.path.chmod(0o600)
        set_value(self.path, "TOKEN", "new")
        self.assertEqual(load(self.path), {"TOKEN": "new"})
        self.assertEqual(self.path.read_text().count("TOKEN="), 1)

    def test_reads_common_dotenv_quotes_and_comments(self):
        self.path.write_text(
            'DOUBLE="hello world" # comment\n'
            "SINGLE='it\\'s private' # comment\n"
            "PLAIN=value # comment\n"
            "URL=https://example.com/#fragment\n",
            encoding="utf-8",
        )
        self.path.chmod(0o600)
        self.assertEqual(
            load(self.path),
            {
                "DOUBLE": "hello world",
                "SINGLE": "it's private",
                "PLAIN": "value",
                "URL": "https://example.com/#fragment",
            },
        )

    def test_unset_preserves_other_lines(self):
        self.path.write_text("# note\nA=1\nB=2\n", encoding="utf-8")
        self.path.chmod(0o600)
        self.assertTrue(unset_value(self.path, "A"))
        self.assertFalse(unset_value(self.path, "A"))
        self.assertEqual(load(self.path), {"B": "2"})
        self.assertIn("# note", self.path.read_text())

    def test_invalid_name_is_rejected(self):
        with self.assertRaises(StoreError):
            set_value(self.path, "BAD-NAME", "value")

    def test_nul_value_is_rejected(self):
        with self.assertRaises(StoreError):
            set_value(self.path, "TOKEN", "before\x00after")

    def test_malformed_assignment_is_rejected(self):
        self.path.write_text("GOOD=value\nBAD-NAME=value\n", encoding="utf-8")
        with self.assertRaises(StoreError):
            load(self.path)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions")
    def test_owner_only_permissions(self):
        initialize(self.path)
        set_value(self.path, "TOKEN", "secret")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_default_path_is_agent_independent(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp.name}, clear=True):
            self.assertEqual(default_path(), Path(self.temp.name) / "envskill" / "secrets.env")

    def test_empty_xdg_config_home_does_not_use_current_directory(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=True):
            self.assertEqual(default_path(), Path.home() / ".config" / "envskill" / "secrets.env")

    @unittest.skipUnless(os.name == "posix", "POSIX permissions and symlinks")
    def test_insecure_and_symlinked_stores_are_rejected(self):
        self.path.write_text('TOKEN="secret"\n', encoding="utf-8")
        self.path.chmod(0o644)
        with self.assertRaises(StoreError):
            validate_store(self.path)

        self.path.chmod(0o700)
        with self.assertRaises(StoreError):
            validate_store(self.path)

        initialize(self.path)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

        link = Path(self.temp.name) / "link.env"
        link.symlink_to(self.path)
        with self.assertRaises(StoreError):
            initialize(link)

    @unittest.skipUnless(os.name == "posix", "POSIX directory permissions")
    def test_world_writable_store_parent_is_rejected(self):
        parent = Path(self.temp.name) / "unsafe"
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        with self.assertRaises(StoreError):
            initialize(parent / "secrets.env")

    @unittest.skipUnless(os.name == "posix", "fcntl locking is POSIX-specific")
    def test_kernel_lock_serializes_a_writer(self):
        script = (
            "import sys,time; from pathlib import Path; "
            "from envskill.store import _store_lock; "
            "lock=_store_lock(Path(sys.argv[1])); lock.__enter__(); "
            "print('locked', flush=True); time.sleep(0.5); lock.__exit__(None,None,None)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(self.path)],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIsNotNone(process.stdout)
        self.assertEqual(process.stdout.readline().strip(), "locked")
        started = time.monotonic()
        set_value(self.path, "TOKEN", "value")
        elapsed = time.monotonic() - started
        self.assertEqual(process.wait(timeout=2), 0)
        process.stdout.close()
        self.assertGreaterEqual(elapsed, 0.3)


if __name__ == "__main__":
    unittest.main()
