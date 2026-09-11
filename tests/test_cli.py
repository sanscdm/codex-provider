from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codex_provider.cli import deepseek_api_key, main
from codex_provider.core import ProviderError
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
        self.assertIn("Next: codex-provider use deepseek", output.getvalue())

    def test_noninteractive_install_has_actionable_error(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch(
            "codex_provider.cli.getpass.getpass", side_effect=EOFError
        ):
            with self.assertRaisesRegex(ProviderError, "Set DEEPSEEK_API_KEY"):
                deepseek_api_key()


if __name__ == "__main__":
    unittest.main()
