from __future__ import annotations

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
        self.paths.config.write_text(
            '[model_providers.deepseek]\nbase_url = "https://api.deepseek.com/"\n',
            encoding="utf-8",
        )
        (self.paths.codex_home / "deepseek.config.toml").write_text(
            'model = "deepseek-flash"\n'
            'model_provider = "deepseek"\n'
            'model_catalog_json = "./deepseek.models.json"\n'
            '\n[mcp_servers.linear.tools.save_comment]\n'
            'approval_mode = "approve"\n',
            encoding="utf-8",
        )
        environment = self.paths.provider_environment("deepseek")
        environment.parent.mkdir(parents=True)
        environment.write_text(
            f"export DEEPSEEK_API_KEY={TEST_KEY}\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_run_uses_selection_overrides_and_ignores_saved_profile_permissions(self) -> None:
        completed = type("Completed", (), {"returncode": 0})()
        with patch("codex_provider.runner.subprocess.run", return_value=completed) as run:
            exit_code = run_codex(
                self.paths,
                "deepseek",
                ["--", "--ephemeral"],
                executable=Path("/opt/codex/bin/codex"),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            run.call_args.args[0],
            [
                "/opt/codex/bin/codex",
                "-c",
                'model="deepseek-flash"',
                "-c",
                'model_provider="deepseek"',
                "-c",
                f'model_catalog_json="{(self.paths.codex_home / "deepseek.models.json").resolve()}"',
                "--ephemeral",
            ],
        )
        self.assertNotIn("--profile", run.call_args.args[0])

    def test_missing_codex_cli_has_actionable_error(self) -> None:
        with patch("codex_provider.runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ProviderError, "Codex CLI not found"):
                run_codex(self.paths, "deepseek")

    def test_openrouter_run_uses_selection_without_a_local_catalog(self) -> None:
        self.paths.config.write_text(
            '[model_providers.openrouter]\nbase_url = "https://openrouter.ai/api/v1"\n',
            encoding="utf-8",
        )
        (self.paths.codex_home / "openrouter.config.toml").write_text(
            'model = "~openai/gpt-latest"\n'
            'model_provider = "openrouter"\n'
            'model_reasoning_effort = "high"\n',
            encoding="utf-8",
        )
        completed = type("Completed", (), {"returncode": 0})()
        with patch("codex_provider.runner.subprocess.run", return_value=completed) as run:
            exit_code = run_codex(
                self.paths,
                "openrouter",
                executable=Path("/opt/codex/bin/codex"),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            run.call_args.args[0],
            [
                "/opt/codex/bin/codex",
                "-c",
                'model="~openai/gpt-latest"',
                "-c",
                'model_provider="openrouter"',
                "-c",
                'model_reasoning_effort="high"',
            ],
        )
        self.assertNotIn("model_catalog_json", " ".join(run.call_args.args[0]))

    def test_missing_profile_stops_before_launch(self) -> None:
        with self.assertRaisesRegex(ProviderError, "profile not found"):
            run_codex(
                self.paths,
                "missing",
                executable=Path("/opt/codex/bin/codex"),
            )


if __name__ == "__main__":
    unittest.main()
