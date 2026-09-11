from __future__ import annotations

import unittest
from pathlib import Path

from codex_provider.desktop import jxa_source


class DesktopSourceTestCase(unittest.TestCase):
    def test_launcher_uses_installed_executable_and_safe_profile_menu(self) -> None:
        source = jxa_source(Path("bin/codex-provider"))
        self.assertIn('const executable = "bin/codex-provider"', source)
        self.assertIn('" names"', source)
        self.assertIn("Restore original", source)
        self.assertIn("Use Codex defaults", source)
        self.assertNotIn("/" + "Users/", source)


if __name__ == "__main__":
    unittest.main()
