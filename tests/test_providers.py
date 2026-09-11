from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from codex_provider.core import Paths, ProviderError
from codex_provider.providers import (
    CATALOG_END,
    CATALOG_START,
    install_deepseek,
    read_environment,
    validate_deepseek_api_key,
    verify_official_setup_script,
)


TEST_KEY = "sk-" + "testvalue123456"
CATALOG = {
    "models": [
        {"slug": "deepseek-flash", "display_name": "DeepSeek Flash"},
        {"slug": "deepseek-v4-pro", "display_name": "DeepSeek V4 Pro"},
    ]
}
SETUP_SCRIPT = CATALOG_START + json.dumps(CATALOG).encode() + CATALOG_END


class DeepSeekInstallerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        self.paths.config.write_text(
            'model = "gpt-6-astra"\n\n[mcp_servers.example]\nurl = "https://example.invalid"\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_install_writes_complete_setup_without_leaking_key(self) -> None:
        result = install_deepseek(
            self.paths,
            TEST_KEY,
            setup_script=SETUP_SCRIPT,
            credential_command="/opt/bin/codex-provider",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        profile = result.profile.read_text(encoding="utf-8")
        catalog = result.catalog.read_text(encoding="utf-8")
        original = self.paths.original.read_text(encoding="utf-8")
        environment = result.environment.read_text(encoding="utf-8")

        self.assertIn("[model_providers.deepseek]", config)
        self.assertIn("[model_providers.deepseek.auth]", config)
        self.assertIn('command = "/opt/bin/codex-provider"', config)
        self.assertIn('args = ["credential", "deepseek"]', config)
        self.assertIn("[mcp_servers.example]", config)
        self.assertIn('model = "deepseek-flash"', profile)
        self.assertEqual({item["slug"] for item in json.loads(catalog)["models"]}, {
            "deepseek-flash",
            "deepseek-v4-pro",
        })
        self.assertIn('model = "gpt-6-astra"', original)
        self.assertEqual(environment, f"export DEEPSEEK_API_KEY={TEST_KEY}\n")
        self.assertEqual(stat.S_IMODE(result.environment.stat().st_mode), 0o600)
        for public_text in (config, profile, catalog, original):
            self.assertNotIn(TEST_KEY, public_text)

    def test_install_replaces_insecure_existing_deepseek_auth(self) -> None:
        token_key = "experimental_" + "bearer_token"
        self.paths.config.write_text(
            "[model_providers.deepseek]\n"
            'base_url = "https://old.invalid"\n'
            f'{token_key} = "old-value"\n'
            "[model_providers.deepseek.auth]\n"
            'command = "security"\n',
            encoding="utf-8",
        )

        install_deepseek(
            self.paths,
            TEST_KEY,
            setup_script=SETUP_SCRIPT,
            credential_command="/opt/bin/codex-provider",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        self.assertNotIn(token_key, config)
        self.assertNotIn("old-value", config)
        self.assertNotIn("env_key", config)
        self.assertIn("[model_providers.deepseek.auth]", config)

    def test_invalid_key_stops_before_any_write(self) -> None:
        before = self.paths.config.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ProviderError, "must start with sk-"):
            install_deepseek(
                self.paths,
                "invalid value",
                setup_script=SETUP_SCRIPT,
            )
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)
        self.assertFalse(self.paths.data_home.exists())

    def test_catalog_with_unexpected_model_stops_before_write(self) -> None:
        catalog = {"models": [{"slug": "unexpected-model"}]}
        script = CATALOG_START + json.dumps(catalog).encode() + CATALOG_END
        with self.assertRaisesRegex(ProviderError, "unexpected model set"):
            install_deepseek(
                self.paths,
                TEST_KEY,
                setup_script=script,
            )
        self.assertFalse(self.paths.data_home.exists())

    def test_stored_environment_can_supply_command_backed_auth(self) -> None:
        environment = self.paths.provider_environment("deepseek")
        environment.parent.mkdir(parents=True)
        environment.write_text(
            f"export DEEPSEEK_API_KEY={TEST_KEY}\n",
            encoding="utf-8",
        )
        self.assertEqual(read_environment(environment), TEST_KEY)

    def test_key_validation_rejects_shell_syntax(self) -> None:
        with self.assertRaises(ProviderError):
            validate_deepseek_api_key("sk-value;command")

    def test_changed_official_script_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProviderError, "changed its setup script"):
            verify_official_setup_script(b"changed")


if __name__ == "__main__":
    unittest.main()
