from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_provider.core import (
    BEGIN_MARKER,
    Paths,
    ProviderError,
    initialize,
    list_profiles,
    restore_original,
    rollback,
    status,
    use_defaults,
    use_profile,
)


BASE_CONFIG = '''model = "magnitude-local"
model_provider = "magnitude"
model_catalog_json = "magnitude.models.json"
web_search = "cached"

[model_providers.magnitude]
name = "Local inference"
base_url = "http://127.0.0.1:10100/inference/v1/proxies/codex"
wire_api = "responses"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com/"
wire_api = "responses"
env_key = "DEEPSEEK_API_KEY"

[mcp_servers.example]
url = "https://example.invalid/mcp"
'''

DEEPSEEK_PROFILE = '''model = "deepseek-flash"
model_provider = "deepseek"
model_catalog_json = "./deepseek.models.json"
model_reasoning_effort = "high"
web_search = "disabled"
'''


class ProviderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / ".codex", root / ".codex-provider")
        self.paths.codex_home.mkdir()
        self.paths.config.write_text(BASE_CONFIG, encoding="utf-8")
        (self.paths.codex_home / "deepseek.config.toml").write_text(
            DEEPSEEK_PROFILE, encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_switch_restore_preserves_original_catalog_and_unrelated_config(self) -> None:
        initialize(self.paths)
        use_profile(self.paths, "deepseek")
        switched = self.paths.config.read_text(encoding="utf-8")
        self.assertIn(BEGIN_MARKER, switched)
        self.assertIn('model = "deepseek-flash"', switched)
        self.assertIn('model_catalog_json = "./deepseek.models.json"', switched)
        self.assertIn("[mcp_servers.example]", switched)

        restore_original(self.paths)
        restored = self.paths.config.read_text(encoding="utf-8")
        self.assertIn('model = "magnitude-local"', restored)
        self.assertIn('model_catalog_json = "magnitude.models.json"', restored)
        self.assertIn("[model_providers.deepseek]", restored)
        self.assertIn("[mcp_servers.example]", restored)

    def test_default_removes_only_selection(self) -> None:
        initialize(self.paths)
        use_defaults(self.paths)
        current = self.paths.config.read_text(encoding="utf-8")
        self.assertNotIn("model_catalog_json", current)
        self.assertIn("[model_providers.magnitude]", current)
        self.assertIn("[mcp_servers.example]", current)

    def test_rollback_restores_selection_before_last_switch(self) -> None:
        initialize(self.paths)
        use_profile(self.paths, "deepseek")
        snapshot, provider = rollback(self.paths)
        self.assertTrue(snapshot.exists())
        self.assertEqual(provider, "magnitude")
        current = self.paths.config.read_text(encoding="utf-8")
        self.assertIn('model_catalog_json = "magnitude.models.json"', current)

    def test_custom_provider_must_exist_in_base_config(self) -> None:
        profile = self.paths.codex_home / "missing.config.toml"
        profile.write_text('model_provider = "missing"\nmodel = "sample"\n', encoding="utf-8")
        with self.assertRaisesRegex(ProviderError, "not defined"):
            use_profile(self.paths, "missing")

    def test_profile_name_rejects_shell_characters(self) -> None:
        with self.assertRaisesRegex(ProviderError, "Profile names"):
            use_profile(self.paths, "deepseek;open")

    def test_list_and_status_are_deterministic(self) -> None:
        initialize(self.paths)
        self.assertEqual(list_profiles(self.paths), ["deepseek"])
        report = status(self.paths)
        self.assertEqual(report["active"], "original")
        self.assertEqual(report["selection"]["model_provider"], "magnitude")
        json.dumps(report)

    def test_malformed_managed_block_fails_closed(self) -> None:
        self.paths.config.write_text(
            f"{BEGIN_MARKER}\nmodel = \"broken\"\n" + BASE_CONFIG,
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProviderError, "Malformed"):
            use_defaults(self.paths)


if __name__ == "__main__":
    unittest.main()
