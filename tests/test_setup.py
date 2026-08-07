import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from envskill.setup import detect_agents, resolve_agents


class SetupSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_detect_agents_uses_install_markers_and_executables_only(self):
        (self.home / ".codex").mkdir()

        def which(name):
            return "/usr/local/bin/claude" if name == "claude" else None

        with patch.dict(os.environ, {"HERMES_HOME": str(self.home / ".hermes")}, clear=False):
            self.assertEqual(detect_agents(home=self.home, which=which), ["codex", "claude"])

    def test_resolve_agents_supports_auto_single_agent_and_all(self):
        self.assertEqual(resolve_agents("auto", ["hermes", "codex"]), ["hermes", "codex"])
        self.assertEqual(resolve_agents("claude", ["codex"]), ["claude"])
        self.assertEqual(resolve_agents("all", []), ["codex", "claude", "hermes"])


if __name__ == "__main__":
    unittest.main()
