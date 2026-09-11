from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlparse

import tomlkit
from tomlkit.items import Table

from .core import (
    Paths,
    ProviderError,
    atomic_write,
    ensure_initialized,
    locked,
    parse_toml,
)


DEEPSEEK_SETUP_URL = "https://cdn.deepseek.com/api-docs/codex-deepseek-setup-en.sh"
DEEPSEEK_SETUP_SHA256 = "ee0119610037ef8fc4cf05899109dec1530ad900730fd29797da751afd85953e"
DEEPSEEK_MODELS = frozenset({"deepseek-flash", "deepseek-v4-pro"})
DEEPSEEK_ENVIRONMENT_KEY = "DEEPSEEK_API_KEY"
DEEPSEEK_CATALOG_NAME = "deepseek.models.json"
DEEPSEEK_PROFILE_NAME = "deepseek"
OPENROUTER_ENVIRONMENT_KEY = "OPENROUTER_API_KEY"
OPENROUTER_PROFILE_NAME = "openrouter"
OPENROUTER_DEFAULT_MODEL = "~openai/gpt-latest"
MAX_SETUP_BYTES = 2_000_000
API_KEY = re.compile(r"^sk-[A-Za-z0-9._-]{8,}$")
OPENROUTER_API_KEY = re.compile(r"^sk-or-[A-Za-z0-9._-]{8,}$")
CATALOG_START = b"cat > \"$1\" <<'CODEX_MODELS_JSON'\n"
CATALOG_END = b"\nCODEX_MODELS_JSON\n"


def provider_environment_key(provider: str) -> str:
    if provider == DEEPSEEK_PROFILE_NAME:
        return DEEPSEEK_ENVIRONMENT_KEY
    if provider == OPENROUTER_PROFILE_NAME:
        return OPENROUTER_ENVIRONMENT_KEY
    raise ProviderError(f"Unsupported provider: {provider}")


def provider_display_name(provider: str) -> str:
    if provider == DEEPSEEK_PROFILE_NAME:
        return "DeepSeek"
    if provider == OPENROUTER_PROFILE_NAME:
        return "OpenRouter"
    raise ProviderError(f"Unsupported provider: {provider}")


@dataclass(frozen=True)
class ProviderInstallResult:
    profile: Path
    catalog: Path | None
    environment: Path


def validate_deepseek_api_key(api_key: str) -> str:
    value = api_key.strip()
    if not API_KEY.fullmatch(value):
        raise ProviderError("DeepSeek API key must start with sk- and contain no spaces")
    return value


def validate_openrouter_api_key(api_key: str) -> str:
    value = api_key.strip()
    if not OPENROUTER_API_KEY.fullmatch(value):
        raise ProviderError(
            "OpenRouter API key must start with sk-or- and contain no spaces"
        )
    return value


def validate_openrouter_model(model: str) -> str:
    value = model.strip()
    if (
        not value
        or len(value) > 200
        or any(
            character.isspace() or not character.isprintable()
            for character in value
        )
    ):
        raise ProviderError("OpenRouter model must be a valid model slug without spaces")
    return value


def verify_official_setup_script(content: bytes) -> None:
    digest = hashlib.sha256(content).hexdigest()
    if digest != DEEPSEEK_SETUP_SHA256:
        raise ProviderError(
            "DeepSeek changed its setup script. Update codex-provider before installing."
        )


def download_official_setup_script() -> bytes:
    request = urllib.request.Request(
        DEEPSEEK_SETUP_URL,
        headers={"User-Agent": "codex-provider/0.2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            final_url = response.geturl()
            content = response.read(MAX_SETUP_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise ProviderError("Could not download the official DeepSeek catalog source") from error

    parsed = urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname != "cdn.deepseek.com":
        raise ProviderError("DeepSeek catalog download redirected to an untrusted host")
    if len(content) > MAX_SETUP_BYTES:
        raise ProviderError("DeepSeek catalog source is larger than the allowed limit")
    verify_official_setup_script(content)
    return content


def extract_deepseek_catalog(setup_script: bytes) -> str:
    start = setup_script.find(CATALOG_START)
    if start < 0:
        raise ProviderError("DeepSeek catalog start marker was not found")
    start += len(CATALOG_START)
    end = setup_script.find(CATALOG_END, start)
    if end < 0:
        raise ProviderError("DeepSeek catalog end marker was not found")

    try:
        data = json.loads(setup_script[start:end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderError("DeepSeek catalog is not valid JSON") from error

    models = data.get("models") if isinstance(data, Mapping) else None
    if not isinstance(models, list):
        raise ProviderError("DeepSeek catalog has no model list")
    slugs = {
        item.get("slug")
        for item in models
        if isinstance(item, Mapping) and isinstance(item.get("slug"), str)
    }
    if slugs != DEEPSEEK_MODELS or len(models) != len(DEEPSEEK_MODELS):
        raise ProviderError("DeepSeek catalog contains an unexpected model set")
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_deepseek_profile(model: str) -> str:
    if model not in DEEPSEEK_MODELS:
        raise ProviderError(f"Unsupported DeepSeek model: {model}")
    return (
        f'model = {json.dumps(model)}\n'
        'model_provider = "deepseek"\n'
        f'model_catalog_json = "./{DEEPSEEK_CATALOG_NAME}"\n'
        'model_reasoning_effort = "high"\n'
        'web_search = "disabled"\n'
    )


def render_openrouter_profile(model: str) -> str:
    value = validate_openrouter_model(model)
    return (
        f'model = {json.dumps(value)}\n'
        'model_provider = "openrouter"\n'
        'model_reasoning_effort = "high"\n'
        'web_search = "disabled"\n'
    )


def configure_provider(
    config_text: str,
    *,
    provider: str,
    display_name: str,
    base_url: str,
    credential_command: str,
) -> str:
    parse_toml(config_text, "Codex configuration")
    document = tomlkit.parse(config_text)
    providers = document.get("model_providers")
    if providers is None:
        providers = tomlkit.table()
        document["model_providers"] = providers
    if not isinstance(providers, Table):
        raise ProviderError("model_providers must be a TOML table")

    definition = tomlkit.table()
    definition.add("name", display_name)
    definition.add("base_url", base_url)
    definition.add("wire_api", "responses")
    authentication = tomlkit.table()
    authentication.add("command", credential_command)
    authentication.add("args", ["credential", provider])
    definition.add("auth", authentication)
    providers[provider] = definition

    candidate = tomlkit.dumps(document)
    parse_toml(candidate, "generated Codex configuration")
    return candidate


def configure_deepseek_provider(
    config_text: str,
    credential_command: str = "codex-provider",
) -> str:
    return configure_provider(
        config_text,
        provider=DEEPSEEK_PROFILE_NAME,
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/",
        credential_command=credential_command,
    )


def configure_openrouter_provider(
    config_text: str,
    credential_command: str = "codex-provider",
) -> str:
    return configure_provider(
        config_text,
        provider=OPENROUTER_PROFILE_NAME,
        display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        credential_command=credential_command,
    )


def render_environment(environment_key: str, api_key: str) -> str:
    return f"export {environment_key}={api_key}\n"


def read_environment(path: Path, environment_key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ProviderError(f"Provider environment not found: {path}") from error
    prefix = f"export {environment_key}="
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].startswith(prefix):
        raise ProviderError(f"Invalid provider environment: {path}")
    value = lines[0][len(prefix) :]
    if environment_key == DEEPSEEK_ENVIRONMENT_KEY:
        return validate_deepseek_api_key(value)
    if environment_key == OPENROUTER_ENVIRONMENT_KEY:
        return validate_openrouter_api_key(value)
    raise ProviderError(f"Unsupported provider environment key: {environment_key}")


def write_provider_install(
    paths: Paths,
    *,
    provider: str,
    profile_text: str,
    environment_text: str,
    configure: Callable[[str], str],
    catalog_name: str | None = None,
    catalog_text: str | None = None,
) -> ProviderInstallResult:
    profile = paths.codex_home / f"{provider}.config.toml"
    environment = paths.provider_environment(provider)
    catalog = paths.codex_home / catalog_name if catalog_name else None
    with locked(paths):
        paths.codex_home.mkdir(parents=True, exist_ok=True)
        if not paths.config.exists():
            atomic_write(paths.config, "")
        ensure_initialized(paths)
        config_text = paths.config.read_text(encoding="utf-8")
        candidate = configure(config_text)
        if catalog is not None and catalog_text is not None:
            atomic_write(catalog, catalog_text)
        atomic_write(profile, profile_text)
        atomic_write(environment, environment_text)
        atomic_write(paths.config, candidate)
    return ProviderInstallResult(profile, catalog, environment)


def install_deepseek(
    paths: Paths,
    api_key: str,
    model: str = "deepseek-flash",
    *,
    setup_script: bytes | None = None,
    credential_command: str = "codex-provider",
) -> ProviderInstallResult:
    value = validate_deepseek_api_key(api_key)
    source = setup_script if setup_script is not None else download_official_setup_script()
    catalog_text = extract_deepseek_catalog(source)
    profile_text = render_deepseek_profile(model)
    environment_text = render_environment(DEEPSEEK_ENVIRONMENT_KEY, value)
    return write_provider_install(
        paths,
        provider=DEEPSEEK_PROFILE_NAME,
        profile_text=profile_text,
        environment_text=environment_text,
        configure=lambda config: configure_deepseek_provider(
            config, credential_command
        ),
        catalog_name=DEEPSEEK_CATALOG_NAME,
        catalog_text=catalog_text,
    )


def install_openrouter(
    paths: Paths,
    api_key: str,
    model: str = OPENROUTER_DEFAULT_MODEL,
    *,
    credential_command: str = "codex-provider",
) -> ProviderInstallResult:
    value = validate_openrouter_api_key(api_key)
    return write_provider_install(
        paths,
        provider=OPENROUTER_PROFILE_NAME,
        profile_text=render_openrouter_profile(model),
        environment_text=render_environment(OPENROUTER_ENVIRONMENT_KEY, value),
        configure=lambda config: configure_openrouter_provider(
            config, credential_command
        ),
    )
