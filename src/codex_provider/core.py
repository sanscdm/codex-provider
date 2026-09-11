from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9 and 3.10
    import tomli as tomllib  # type: ignore[no-redef]


MANAGED_KEYS = (
    "model",
    "model_provider",
    "model_catalog_json",
    "model_reasoning_effort",
    "model_reasoning_summary",
    "model_verbosity",
    "service_tier",
    "web_search",
    "oss_provider",
    "openai_base_url",
)
MANAGED_KEY_SET = frozenset(MANAGED_KEYS)
BEGIN_MARKER = "# >>> codex-provider managed selection >>>"
END_MARKER = "# <<< codex-provider managed selection <<<"
PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ASSIGNMENT = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
BUILT_IN_PROVIDERS = frozenset({"openai", "amazon-bedrock", "ollama", "lmstudio"})


class ProviderError(RuntimeError):
    """A safe, user-facing provider configuration error."""


@dataclass(frozen=True)
class Paths:
    codex_home: Path
    data_home: Path

    @classmethod
    def discover(cls) -> "Paths":
        codex_home_value = os.environ.get("CODEX_HOME")
        data_home_value = os.environ.get("CODEX_PROVIDER_HOME")
        codex_home = (
            Path(codex_home_value).expanduser()
            if codex_home_value
            else Path.home() / ".codex"
        )
        data_home = (
            Path(data_home_value).expanduser()
            if data_home_value
            else Path.home() / ".codex-provider"
        )
        return cls(codex_home=codex_home, data_home=data_home)

    @property
    def config(self) -> Path:
        return self.codex_home / "config.toml"

    @property
    def snapshots(self) -> Path:
        return self.data_home / "snapshots"

    @property
    def original(self) -> Path:
        return self.data_home / "original.toml"

    @property
    def state(self) -> Path:
        return self.data_home / "state.json"

    @property
    def lock(self) -> Path:
        return self.data_home / "switch.lock"


def parse_toml(text: str, source: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ProviderError(f"Invalid TOML in {source}: {error}") from error


def load_toml(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ProviderError(f"File not found: {path}") from error
    validate_markers(text)
    return text, parse_toml(text, str(path))


def selection_from_data(data: Mapping[str, Any]) -> dict[str, Any]:
    selection: dict[str, Any] = {}
    for key in MANAGED_KEYS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, (str, bool, int)) or isinstance(value, float):
            raise ProviderError(
                f"Unsupported value for {key}; expected a string, integer, or boolean"
            )
        selection[key] = value
    return selection


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise ProviderError(f"Unsupported selection value: {value!r}")


def render_selection(selection: Mapping[str, Any]) -> str:
    lines = [f"{key} = {format_value(selection[key])}" for key in MANAGED_KEYS if key in selection]
    return "\n".join(lines) + ("\n" if lines else "")


def validate_markers(text: str) -> None:
    begin_count = text.count(BEGIN_MARKER)
    end_count = text.count(END_MARKER)
    if begin_count != end_count or begin_count > 1:
        raise ProviderError(
            "Malformed codex-provider managed block; restore config.toml from a trusted copy"
        )


def strip_managed_selection(text: str) -> str:
    validate_markers(text)

    lines = text.splitlines(keepends=True)
    result: list[str] = []
    in_managed_block = False
    in_top_level = True

    for line in lines:
        stripped = line.strip()
        if stripped == BEGIN_MARKER:
            in_managed_block = True
            continue
        if stripped == END_MARKER:
            in_managed_block = False
            continue
        if in_managed_block:
            continue

        if line.lstrip().startswith("["):
            in_top_level = False

        match = ASSIGNMENT.match(line) if in_top_level else None
        if match and match.group(1) in MANAGED_KEY_SET:
            continue
        result.append(line)

    return "".join(result).lstrip("\n")


def apply_selection(text: str, selection: Mapping[str, Any]) -> str:
    remainder = strip_managed_selection(text)
    if not selection:
        return remainder
    block = f"{BEGIN_MARKER}\n{render_selection(selection)}{END_MARKER}\n\n"
    return block + remainder


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_state(paths: Paths) -> dict[str, Any]:
    if not paths.state.exists():
        return {"version": 1, "active": None, "history": []}
    try:
        data = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProviderError(f"Invalid state file: {paths.state}") from error
    if data.get("version") != 1 or not isinstance(data.get("history"), list):
        raise ProviderError(f"Unsupported state file: {paths.state}")
    return data


@contextmanager
def locked(paths: Paths) -> Iterator[None]:
    paths.data_home.mkdir(parents=True, exist_ok=True)
    paths.lock.touch(mode=0o600, exist_ok=True)
    with paths.lock.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def snapshot_name(target: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_target = re.sub(r"[^A-Za-z0-9_-]", "-", target)
    return f"{stamp}-before-{safe_target}.toml"


def save_snapshot(paths: Paths, selection: Mapping[str, Any], target: str) -> Path:
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    path = paths.snapshots / snapshot_name(target)
    atomic_write(path, render_selection(selection))
    return path


def profile_path(paths: Paths, name: str) -> Path:
    if not PROFILE_NAME.fullmatch(name):
        raise ProviderError(
            "Profile names must use only letters, numbers, hyphens, and underscores"
        )
    return paths.codex_home / f"{name}.config.toml"


def list_profiles(paths: Paths) -> list[str]:
    if not paths.codex_home.exists():
        return []
    suffix = ".config.toml"
    return sorted(
        path.name[: -len(suffix)]
        for path in paths.codex_home.glob(f"*{suffix}")
        if PROFILE_NAME.fullmatch(path.name[: -len(suffix)])
    )


def validate_profile_for_desktop(
    name: str,
    profile_data: Mapping[str, Any],
    base_data: Mapping[str, Any],
) -> dict[str, Any]:
    selection = selection_from_data(profile_data)
    if not selection:
        raise ProviderError(f"Profile {name!r} has no provider selection settings")

    provider = selection.get("model_provider")
    if isinstance(provider, str) and provider not in BUILT_IN_PROVIDERS:
        definitions = base_data.get("model_providers", {})
        if not isinstance(definitions, Mapping) or provider not in definitions:
            raise ProviderError(
                f"Profile {name!r} selects custom provider {provider!r}, but "
                "that provider is not defined in the base ~/.codex/config.toml"
            )
    return selection


def initialize(paths: Paths, original_config: Path | None = None, force: bool = False) -> Path:
    with locked(paths):
        if paths.original.exists() and not force:
            raise ProviderError(
                f"Original snapshot already exists: {paths.original}. Use --force to replace it."
            )
        source = original_config or paths.config
        _, data = load_toml(source)
        selection = selection_from_data(data)
        if paths.original.exists():
            _, previous_data = load_toml(paths.original)
            save_snapshot(
                paths,
                selection_from_data(previous_data),
                "original-reset",
            )
        atomic_write(paths.original, render_selection(selection))
        state = read_state(paths)
        state["active"] = "original"
        write_json(paths.state, state)
        return paths.original


def ensure_initialized(paths: Paths) -> None:
    if not paths.original.exists():
        _, data = load_toml(paths.config)
        atomic_write(paths.original, render_selection(selection_from_data(data)))
    if not paths.state.exists():
        write_json(paths.state, {"version": 1, "active": "original", "history": []})


def switch_to_selection(paths: Paths, selection: Mapping[str, Any], target: str) -> Path:
    with locked(paths):
        ensure_initialized(paths)
        config_text, _ = load_toml(paths.config)
        current_data = parse_toml(config_text, str(paths.config))
        current = selection_from_data(current_data)
        snapshot = save_snapshot(paths, current, target)

        candidate = apply_selection(config_text, selection)
        parse_toml(candidate, "generated Codex configuration")
        atomic_write(paths.config, candidate)

        state = read_state(paths)
        history = state.setdefault("history", [])
        history.append(snapshot.name)
        state["active"] = target
        write_json(paths.state, state)
        return snapshot


def use_profile(paths: Paths, name: str) -> Path:
    profile = profile_path(paths, name)
    _, profile_data = load_toml(profile)
    _, base_data = load_toml(paths.config)
    selection = validate_profile_for_desktop(name, profile_data, base_data)
    return switch_to_selection(paths, selection, name)


def restore_original(paths: Paths) -> Path:
    if not paths.original.exists():
        raise ProviderError("No original snapshot exists. Run codex-provider init first.")
    _, original_data = load_toml(paths.original)
    return switch_to_selection(paths, selection_from_data(original_data), "original")


def use_defaults(paths: Paths) -> Path:
    return switch_to_selection(paths, {}, "default")


def rollback(paths: Paths) -> tuple[Path, str | None]:
    with locked(paths):
        ensure_initialized(paths)
        state = read_state(paths)
        history = state.get("history", [])
        if not history:
            raise ProviderError("No provider switch is available to roll back")
        snapshot_name_value = history.pop()
        snapshot = paths.snapshots / snapshot_name_value
        _, snapshot_data = load_toml(snapshot)
        selection = selection_from_data(snapshot_data)

        config_text, _ = load_toml(paths.config)
        candidate = apply_selection(config_text, selection)
        parse_toml(candidate, "generated Codex configuration")
        atomic_write(paths.config, candidate)

        state["active"] = None
        write_json(paths.state, state)
        return snapshot, selection.get("model_provider")


def status(paths: Paths) -> dict[str, Any]:
    _, data = load_toml(paths.config)
    state = read_state(paths)
    return {
        "active": state.get("active"),
        "selection": selection_from_data(data),
        "profiles": list_profiles(paths),
        "original_snapshot": str(paths.original) if paths.original.exists() else None,
        "rollback_count": len(state.get("history", [])),
    }
