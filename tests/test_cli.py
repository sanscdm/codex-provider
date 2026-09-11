from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codex_provider.cli import main, provider_api_key
from codex_provider.core import Paths, ProviderError
from codex_provider.providers import ProviderInstallResult


TEST_KEY = "sk-" + "testvalue123456"


class CliTestCase(unittest.TestCase):
    def test_install_prompts_without_echoing_key(self) -> None:
        result = ProviderInstallResult(
            Path("profile.toml"),
            Path("catalog.json"),
            Path("deepseek.env"),
        )
        output = io.StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch(
            "codex_provider.cli.getpass.getpass", return_value=TEST_KEY
        ) as prompt, patch(
            "codex_provider.cli.install_deepseek", return_value=result
        ) as install, redirect_stdout(output):
            exit_code = main(["install", "deepseek"])

        self.assertEqual(exit_code, 0)
        prompt.assert_called_once_with("DeepSeek API key: ")
        self.assertEqual(install.call_args.args[1], TEST_KEY)
        self.assertNotIn(TEST_KEY, output.getvalue())
        self.assertIn("Desktop: codex-provider use deepseek", output.getvalue())
        self.assertIn("CLI: codex-provider run deepseek", output.getvalue())

    def test_run_forwards_profile_and_codex_arguments(self) -> None:
        with patch(
            "codex_provider.cli.run_codex", return_value=7
        ) as run:
            exit_code = main(["run", "deepseek", "--", "--ephemeral"])

        self.assertEqual(exit_code, 7)
        self.assertEqual(run.call_args.args[1:], ("deepseek", ["--ephemeral"]))

    def test_noninteractive_install_has_actionable_error(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch(
            "codex_provider.cli.getpass.getpass", side_effect=EOFError
        ):
            with self.assertRaisesRegex(ProviderError, "Set DEEPSEEK_API_KEY"):
                provider_api_key(
                    Paths(Path(".codex"), Path(".codex-provider")), "deepseek"
                )

    def test_install_reuses_stored_key_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = Paths(Path(temporary) / ".codex", Path(temporary) / ".codex-provider")
            environment = paths.provider_environment("deepseek")
            environment.parent.mkdir(parents=True)
            environment.write_text(
                f"export DEEPSEEK_API_KEY={TEST_KEY}\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch(
                "codex_provider.cli.getpass.getpass"
            ) as prompt:
                self.assertEqual(provider_api_key(paths, "deepseek"), TEST_KEY)
            prompt.assert_not_called()

    def test_credential_command_returns_stored_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = Paths(Path(temporary) / ".codex", Path(temporary) / ".codex-provider")
            environment = paths.provider_environment("deepseek")
            environment.parent.mkdir(parents=True)
            environment.write_text(
                f"export DEEPSEEK_API_KEY={TEST_KEY}\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(paths.codex_home),
                    "CODEX_PROVIDER_HOME": str(paths.data_home),
                },
            ), redirect_stdout(output):
                exit_code = main(["credential", "deepseek"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(output.getvalue(), f"{TEST_KEY}\n")

    def test_openrouter_install_accepts_exact_model_slug(self) -> None:
        result = ProviderInstallResult(
            Path("openrouter.config.toml"),
            None,
            Path("openrouter.env"),
        )
        key = "sk-or-v1-testvalue123456"
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": key}), patch(
            "codex_provider.cli.install_openrouter", return_value=result
        ) as install, redirect_stdout(output):
            exit_code = main(
                [
                    "install",
                    "openrouter",
                    "--model",
                    "anthropic/claude-sonnet-4.5",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            install.call_args.args[1:3],
            (key, "anthropic/claude-sonnet-4.5"),
        )
        self.assertNotIn(key, output.getvalue())
        self.assertIn("Desktop: codex-provider use openrouter", output.getvalue())
        self.assertIn("CLI: codex-provider run openrouter", output.getvalue())


if __name__ == "__main__":
    unittest.main()
