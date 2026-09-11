from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_provider.core import Paths, ProviderError
from codex_provider.runner import run_codex


TEST_KEY = "sk-" + "testvalue123456"


class RunnerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        (self.paths.codex_home / "deepseek.config.toml").write_text(
            'model_provider = "deepseek"\n', encoding="utf-8"
        )
        environment = self.paths.provider_environment("deepseek")
        environment.parent.mkdir(parents=True)
        environment.write_text(
            f"export DEEPSEEK_API_KEY={TEST_KEY}\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_run_loads_stored_key_for_codex_child_only(self) -> None:
        completed = type("Completed", (), {"returncode": 0})()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch(
            "codex_provider.runner.subprocess.run", return_value=completed
        ) as run:
            exit_code = run_codex(
                self.paths,
                "deepseek",
                ["--", "--ephemeral"],
                executable=Path("/opt/codex/bin/codex"),
            )

            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "")

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            run.call_args.args[0],
            ["/opt/codex/bin/codex", "--profile", "deepseek", "--ephemeral"],
        )
        self.assertEqual(run.call_args.kwargs["env"]["DEEPSEEK_API_KEY"], TEST_KEY)

    def test_missing_codex_cli_has_actionable_error(self) -> None:
        with patch("codex_provider.runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ProviderError, "Codex CLI not found"):
                run_codex(self.paths, "deepseek")

    def test_missing_profile_stops_before_launch(self) -> None:
        with self.assertRaisesRegex(ProviderError, "profile not found"):
            run_codex(
                self.paths,
                "missing",
                executable=Path("/opt/codex/bin/codex"),
            )


if __name__ == "__main__":
    unittest.main()
