from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .core import Paths, ProviderError, profile_path
from .providers import DEEPSEEK_ENVIRONMENT_KEY, read_environment


def codex_environment(paths: Paths, profile: str) -> dict[str, str]:
    environment = os.environ.copy()
    if profile == "deepseek":
        environment[DEEPSEEK_ENVIRONMENT_KEY] = read_environment(
            paths.provider_environment(profile)
        )
    return environment


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
        [str(codex), "--profile", profile, *command_arguments],
        env=codex_environment(paths, profile),
        check=False,
    )
    return result.returncode
