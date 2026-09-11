from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__
from .core import (
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
from .desktop import current_executable, default_app_path, install_desktop_app
from .providers import (
    activate_stored_environment,
    clear_environment_for_profile,
    install_deepseek,
)


def deepseek_api_key() -> str:
    existing = os.environ.get("DEEPSEEK_API_KEY")
    if existing:
        return existing
    try:
        return getpass.getpass("DeepSeek API key: ")
    except EOFError as error:
        raise ProviderError(
            "No interactive terminal. Set DEEPSEEK_API_KEY and run the command again."
        ) from error


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        prog="codex-provider",
        description="Safely switch the provider selection used by new Codex desktop tasks.",
    )
    command_parser.add_argument("--version", action="version", version=__version__)
    subcommands = command_parser.add_subparsers(dest="command", required=True)

    init_parser = subcommands.add_parser("init", help="capture the original provider selection")
    init_parser.add_argument("--original-config", type=Path)
    init_parser.add_argument("--force", action="store_true")

    subcommands.add_parser("list", help="list native Codex profiles")
    subcommands.add_parser("names", help=argparse.SUPPRESS)
    subcommands.add_parser("status", help="show the current desktop selection")

    use_parser = subcommands.add_parser("use", help="apply a native profile to desktop tasks")
    use_parser.add_argument("profile")

    install_parser = subcommands.add_parser("install", help="install a provider configuration")
    install_parser.add_argument("provider", choices=["deepseek"])
    install_parser.add_argument(
        "--model",
        choices=["deepseek-flash", "deepseek-v4-pro"],
        default="deepseek-flash",
    )

    subcommands.add_parser("restore", help="restore the first captured selection")
    subcommands.add_parser("default", help="remove overrides and use Codex defaults")
    subcommands.add_parser("rollback", help="restore the selection before the last switch")

    desktop_parser = subcommands.add_parser("desktop-install", help="install the macOS switcher app")
    desktop_parser.add_argument("--app-path", type=Path, default=default_app_path())
    desktop_parser.add_argument("--force", action="store_true")
    return command_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    paths = Paths.discover()
    try:
        if args.command == "init":
            snapshot = initialize(paths, args.original_config, args.force)
            print(f"Captured original provider selection: {snapshot}")
        elif args.command in {"list", "names"}:
            profiles = list_profiles(paths)
            if args.command == "names":
                print("\n".join(profiles))
            elif profiles:
                print("Native Codex profiles:")
                for name in profiles:
                    print(f"  {name}")
            else:
                print("No native Codex profiles found.")
        elif args.command == "status":
            print(json.dumps(status(paths), indent=2, sort_keys=True))
        elif args.command == "use":
            activate_stored_environment(paths, args.profile)
            snapshot = use_profile(paths, args.profile)
            clear_environment_for_profile(args.profile)
            print(f"Desktop provider selection: {args.profile}")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "install":
            result = install_deepseek(paths, deepseek_api_key(), args.model)
            print(f"Installed DeepSeek profile: {result.profile}")
            print(f"Installed DeepSeek catalog: {result.catalog}")
            print(f"Stored local environment: {result.environment}")
            print("Next: codex-provider use deepseek")
            print(f"Native CLI shell: source {result.environment}")
        elif args.command == "restore":
            snapshot = restore_original(paths)
            restored_provider = status(paths)["selection"].get("model_provider", "openai")
            if restored_provider == "deepseek":
                activate_stored_environment(paths, "deepseek")
            else:
                clear_environment_for_profile(str(restored_provider))
            print("Restored the original provider selection.")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "default":
            snapshot = use_defaults(paths)
            clear_environment_for_profile("openai")
            print("Removed provider overrides. Codex defaults will apply.")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "rollback":
            snapshot, provider = rollback(paths)
            if provider == "deepseek":
                activate_stored_environment(paths, "deepseek")
            else:
                clear_environment_for_profile(provider or "openai")
            label = provider or "Codex defaults"
            print(f"Rolled back to: {label}")
            print(f"Applied snapshot: {snapshot}")
        elif args.command == "desktop-install":
            destination = install_desktop_app(
                current_executable(), args.app_path.expanduser(), args.force
            )
            print(f"Installed desktop switcher: {destination}")
        return 0
    except ProviderError as error:
        print(f"codex-provider: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("codex-provider: cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
