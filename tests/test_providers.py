from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from codex_provider.core import Paths, ProviderError, parse_toml
from codex_provider.providers import (
    BEDROCK_DEFAULT_MODEL,
    CATALOG_END,
    CATALOG_START,
    DEEPSEEK_ENVIRONMENT_KEY,
    FOUNDRY_ENVIRONMENT_KEY,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_ENVIRONMENT_KEY,
    install_bedrock,
    install_deepseek,
    install_foundry,
    install_openrouter,
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
        self.assertEqual(
            read_environment(environment, DEEPSEEK_ENVIRONMENT_KEY), TEST_KEY
        )

    def test_key_validation_rejects_shell_syntax(self) -> None:
        with self.assertRaises(ProviderError):
            validate_deepseek_api_key("sk-value;command")

    def test_changed_official_script_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProviderError, "changed its setup script"):
            verify_official_setup_script(b"changed")


class OpenRouterInstallerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        self.paths.config.write_text(
            'model = "gpt-6-astra"\n\n'
            '[mcp_servers.example]\nurl = "https://example.invalid"\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_install_writes_selection_and_command_auth_without_catalog(self) -> None:
        key = "sk-or-v1-testvalue123456"
        result = install_openrouter(
            self.paths,
            key,
            "anthropic/claude-sonnet-4.5",
            credential_command="/opt/bin/codex-provider",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        profile = result.profile.read_text(encoding="utf-8")
        environment = result.environment.read_text(encoding="utf-8")

        self.assertIsNone(result.catalog)
        self.assertIn("[model_providers.openrouter]", config)
        self.assertIn('base_url = "https://openrouter.ai/api/v1"', config)
        self.assertIn("[model_providers.openrouter.auth]", config)
        self.assertIn('command = "/opt/bin/codex-provider"', config)
        self.assertIn('args = ["credential", "openrouter"]', config)
        self.assertIn("[mcp_servers.example]", config)
        self.assertIn('model = "anthropic/claude-sonnet-4.5"', profile)
        self.assertIn('model_provider = "openrouter"', profile)
        self.assertNotIn("model_catalog_json", profile)
        self.assertEqual(environment, f"export OPENROUTER_API_KEY={key}\n")
        self.assertEqual(stat.S_IMODE(result.environment.stat().st_mode), 0o600)
        for public_text in (config, profile):
            self.assertNotIn(key, public_text)

    def test_default_model_uses_official_openrouter_alias(self) -> None:
        result = install_openrouter(
            self.paths,
            "sk-or-v1-testvalue123456",
            credential_command="/opt/bin/codex-provider",
        )
        profile = result.profile.read_text(encoding="utf-8")
        self.assertIn(f'model = "{OPENROUTER_DEFAULT_MODEL}"', profile)

    def test_invalid_key_and_model_stop_before_write(self) -> None:
        before = self.paths.config.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ProviderError, "must start with sk-or-"):
            install_openrouter(self.paths, "sk-not-openrouter")
        with self.assertRaisesRegex(ProviderError, "without spaces"):
            install_openrouter(
                self.paths,
                "sk-or-v1-testvalue123456",
                "anthropic/not a model",
            )
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)
        self.assertFalse(self.paths.data_home.exists())


class BedrockInstallerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        self.paths.config.write_text(
            'model = "gpt-6-astra"\n\n'
            '[mcp_servers.example]\nurl = "https://example.invalid"\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_install_uses_built_in_provider_and_aws_credential_chain(self) -> None:
        result = install_bedrock(
            self.paths,
            aws_profile="codex-bedrock",
            region="us-east-2",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        profile = result.profile.read_text(encoding="utf-8")

        self.assertIsNone(result.catalog)
        self.assertIsNone(result.environment)
        self.assertIn("[model_providers.amazon-bedrock.aws]", config)
        self.assertIn('profile = "codex-bedrock"', config)
        self.assertIn('region = "us-east-2"', config)
        self.assertIn("[mcp_servers.example]", config)
        self.assertIn(f'model = "{BEDROCK_DEFAULT_MODEL}"', profile)
        self.assertIn('model_provider = "amazon-bedrock"', profile)
        self.assertNotIn("auth", config)
        self.assertNotIn("AWS_ACCESS_KEY_ID", config)

    def test_install_without_overrides_preserves_base_config(self) -> None:
        before = self.paths.config.read_text(encoding="utf-8")
        install_bedrock(self.paths)
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)

    def test_invalid_region_and_model_stop_before_write(self) -> None:
        before = self.paths.config.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ProviderError, "commercial Region"):
            install_bedrock(self.paths, region="us-gov-west-1")
        with self.assertRaisesRegex(ProviderError, "without spaces"):
            install_bedrock(self.paths, "openai.invalid model")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)
        self.assertFalse(self.paths.data_home.exists())


class FoundryInstallerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        self.paths.config.write_text(
            'model = "gpt-6-astra"\n\n'
            '[mcp_servers.example]\nurl = "https://example.invalid"\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_install_uses_entra_command_without_storing_a_secret(self) -> None:
        result = install_foundry(
            self.paths,
            "https://acme.services.ai.azure.com/openai/v1/",
            "coding-production",
            azure_cli="/opt/homebrew/bin/az",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        profile = result.profile.read_text(encoding="utf-8")

        self.assertIsNone(result.catalog)
        self.assertIsNone(result.environment)
        self.assertIn("[model_providers.azure-foundry]", config)
        self.assertIn(
            'base_url = "https://acme.services.ai.azure.com/openai/v1"',
            config,
        )
        self.assertIn("[model_providers.azure-foundry.auth]", config)
        self.assertIn('command = "/opt/homebrew/bin/az"', config)
        self.assertIn('"https://ai.azure.com"', config)
        self.assertIn("[mcp_servers.example]", config)
        self.assertIn('model = "coding-production"', profile)
        self.assertIn('model_provider = "azure-foundry"', profile)
        self.assertNotIn("AZURE_OPENAI_API_KEY", config)

    def test_install_supports_project_endpoint(self) -> None:
        result = install_foundry(
            self.paths,
            "https://acme.services.ai.azure.com/api/projects/codex/openai/v1",
            "coding-production",
            azure_cli="/usr/local/bin/az",
        )
        config = self.paths.config.read_text(encoding="utf-8")
        self.assertIn("/api/projects/codex/openai/v1", config)
        self.assertIsNone(result.environment)

    def test_install_supports_api_key_without_leaking_it(self) -> None:
        key = "0123456789abcdef0123456789abcdef"
        result = install_foundry(
            self.paths,
            "https://acme.openai.azure.com/openai/v1",
            "coding-production",
            auth_mode="api-key",
            api_key=key,
            credential_command="/opt/bin/codex-provider",
        )

        config = self.paths.config.read_text(encoding="utf-8")
        profile = result.profile.read_text(encoding="utf-8")
        environment = result.environment.read_text(encoding="utf-8")
        self.assertIn('command = "/opt/bin/codex-provider"', config)
        self.assertIn('args = ["credential", "foundry"]', config)
        self.assertEqual(environment, f"export {FOUNDRY_ENVIRONMENT_KEY}={key}\n")
        self.assertEqual(
            read_environment(result.environment, FOUNDRY_ENVIRONMENT_KEY), key
        )
        self.assertEqual(stat.S_IMODE(result.environment.stat().st_mode), 0o600)
        self.assertNotIn(key, config)
        self.assertNotIn(key, profile)

    def test_entra_reinstall_removes_obsolete_api_key_file(self) -> None:
        key = "0123456789abcdef0123456789abcdef"
        keyed = install_foundry(
            self.paths,
            "https://acme.openai.azure.com/openai/v1",
            "coding-production",
            auth_mode="api-key",
            api_key=key,
            credential_command="/opt/bin/codex-provider",
        )
        self.assertTrue(keyed.environment.is_file())

        result = install_foundry(
            self.paths,
            "https://acme.openai.azure.com/openai/v1",
            "coding-production",
            azure_cli="/usr/local/bin/az",
        )

        self.assertIsNone(result.environment)
        self.assertFalse(self.paths.provider_environment("foundry").exists())

    def test_preview_endpoint_adds_official_api_version(self) -> None:
        install_foundry(
            self.paths,
            "https://acme.openai.azure.com/openai",
            "coding-production",
            azure_cli="/usr/local/bin/az",
        )
        config = self.paths.config.read_text(encoding="utf-8")
        data = parse_toml(config, "test configuration")
        self.assertEqual(
            data["model_providers"]["azure-foundry"]["query_params"]["api-version"],
            "2025-04-01-preview",
        )

    def test_invalid_endpoint_key_and_model_stop_before_write(self) -> None:
        before = self.paths.config.read_text(encoding="utf-8")
        invalid_endpoints = [
            "http://acme.openai.azure.com/openai/v1",
            "https://example.com/openai/v1",
            "https://acme.openai.azure.com:bad/openai/v1",
            "https://acme.openai.azure.com/openai/v1?api-version=secret",
            "https://acme.openai.azure.com/api/projects/codex/openai/v1",
            "https://acme.services.ai.azure.com/openai",
        ]
        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(
                ProviderError, "HTTPS Azure OpenAI"
            ):
                install_foundry(
                    self.paths,
                    endpoint,
                    "coding-production",
                    azure_cli="/usr/local/bin/az",
                )
        unsafe_key = "0123456789abcdef" + ";command"
        with self.assertRaisesRegex(ProviderError, "letters, numbers"):
            install_foundry(
                self.paths,
                "https://acme.openai.azure.com/openai/v1",
                "coding-production",
                auth_mode="api-key",
                api_key=unsafe_key,
                credential_command="/opt/bin/codex-provider",
            )
        with self.assertRaisesRegex(ProviderError, "without spaces"):
            install_foundry(
                self.paths,
                "https://acme.openai.azure.com/openai/v1",
                "invalid deployment",
                azure_cli="/usr/local/bin/az",
            )
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)
        self.assertFalse(self.paths.data_home.exists())


if __name__ == "__main__":
    unittest.main()
