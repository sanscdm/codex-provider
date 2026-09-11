from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .core import (
    Paths,
    ProviderError,
    format_value,
    load_toml,
    profile_path,
    validate_profile_for_desktop,
)


def profile_overrides(paths: Paths, profile: str) -> list[str]:
    profile_file = profile_path(paths, profile)
    _, profile_data = load_toml(profile_file)
    _, base_data = load_toml(paths.config)
    selection = validate_profile_for_desktop(profile, profile_data, base_data)

    catalog = selection.get("model_catalog_json")
    if isinstance(catalog, str):
        catalog_path = Path(catalog)
        if not catalog_path.is_absolute():
            selection["model_catalog_json"] = str(
                (profile_file.parent / catalog_path).resolve()
            )

    overrides: list[str] = []
    for key, value in selection.items():
        overrides.extend(["-c", f"{key}={format_value(value)}"])
    return overrides


def run_codex(
    paths: Paths,
    profile: str,
    arguments: Sequence[str] = (),
    *,
    executable: Path | None = None,
) -> int:
    profile_file = profile_path(paths, profile)
    if not profile_file.is_file():
        raise ProviderError(f"Native Codex profile not found: {profile_file}")

    codex = executable or (Path(found) if (found := shutil.which("codex")) else None)
    if codex is None:
        raise ProviderError(
            "Codex CLI not found. Install it from https://chatgpt.com/codex"
        )

    command_arguments = list(arguments)
    if command_arguments[:1] == ["--"]:
        command_arguments.pop(0)
    result = subprocess.run(
        [str(codex), *profile_overrides(paths, profile), *command_arguments],
        check=False,
    )
    return result.returncode
