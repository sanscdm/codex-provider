from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
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
    BEDROCK_DEFAULT_MODEL,
    BEDROCK_PROFILE_NAME,
    DEEPSEEK_PROFILE_NAME,
    FOUNDRY_PROFILE_NAME,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_PROFILE_NAME,
    install_bedrock,
    install_deepseek,
    install_foundry,
    install_openrouter,
    provider_display_name,
    provider_environment_key,
    read_environment,
)
from .runner import run_codex


def provider_api_key(paths: Paths, provider: str) -> str:
    environment_key = provider_environment_key(provider)
    existing = os.environ.get(environment_key)
    if existing:
        return existing
    stored = paths.provider_environment(provider)
    if stored.is_file():
        return read_environment(stored, environment_key)
    try:
        return getpass.getpass(f"{provider_display_name(provider)} API key: ")
    except EOFError as error:
        raise ProviderError(
            f"No interactive terminal. Set {environment_key} and run the command again."
        ) from error


def reject_cloud_options(args: argparse.Namespace) -> None:
    if args.region or args.aws_profile or args.endpoint or args.auth:
        raise ProviderError(
            "--region, --aws-profile, --endpoint, and --auth apply only to Bedrock or Foundry"
        )


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

    use_parser = subcommands.add_parser("use", help="apply a selection profile to desktop tasks")
    use_parser.add_argument("profile")

    install_parser = subcommands.add_parser("install", help="install a provider configuration")
    install_parser.add_argument(
        "provider", choices=["deepseek", "openrouter", "bedrock", "foundry"]
    )
    install_parser.add_argument("--model")
    install_parser.add_argument("--region")
    install_parser.add_argument("--aws-profile")
    install_parser.add_argument("--endpoint")
    install_parser.add_argument("--auth", choices=["entra", "api-key"])

    run_parser = subcommands.add_parser(
        "run", help="start Codex with temporary overrides from a selection profile"
    )
    run_parser.add_argument("profile")
    run_parser.add_argument("codex_args", nargs=argparse.REMAINDER)

    credential_parser = subcommands.add_parser("credential", help=argparse.SUPPRESS)
    credential_parser.add_argument(
        "provider", choices=["deepseek", "openrouter", "foundry"]
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
            snapshot = use_profile(paths, args.profile)
            print(f"Desktop provider selection: {args.profile}")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "install":
            if args.provider == DEEPSEEK_PROFILE_NAME:
                reject_cloud_options(args)
                result = install_deepseek(
                    paths,
                    provider_api_key(paths, args.provider),
                    args.model or "deepseek-flash",
                    credential_command=str(current_executable()),
                )
            elif args.provider == OPENROUTER_PROFILE_NAME:
                reject_cloud_options(args)
                result = install_openrouter(
                    paths,
                    provider_api_key(paths, args.provider),
                    args.model or OPENROUTER_DEFAULT_MODEL,
                    credential_command=str(current_executable()),
                )
            elif args.provider == BEDROCK_PROFILE_NAME:
                if args.endpoint or args.auth:
                    raise ProviderError(
                        "--endpoint and --auth apply only to Microsoft Foundry"
                    )
                result = install_bedrock(
                    paths,
                    args.model or BEDROCK_DEFAULT_MODEL,
                    aws_profile=args.aws_profile,
                    region=args.region,
                )
            elif args.provider == FOUNDRY_PROFILE_NAME:
                if args.region or args.aws_profile:
                    raise ProviderError(
                        "--region and --aws-profile apply only to Amazon Bedrock"
                    )
                if not args.endpoint:
                    raise ProviderError("Microsoft Foundry requires --endpoint")
                if not args.model:
                    raise ProviderError(
                        "Microsoft Foundry requires --model with the deployment name"
                    )
                auth_mode = args.auth or "entra"
                azure_cli = None
                api_key = None
                credential_command = None
                if auth_mode == "entra":
                    azure_cli = shutil.which("az")
                    if azure_cli is None:
                        raise ProviderError(
                            "Azure CLI not found. Install it, run az login, and try again."
                        )
                else:
                    api_key = provider_api_key(paths, args.provider)
                    credential_command = str(current_executable())
                result = install_foundry(
                    paths,
                    args.endpoint,
                    args.model,
                    auth_mode=auth_mode,
                    api_key=api_key,
                    credential_command=credential_command,
                    azure_cli=azure_cli,
                )
            else:  # pragma: no cover - argparse enforces the provider set
                raise ProviderError(f"Unsupported provider: {args.provider}")
            display_name = provider_display_name(args.provider)
            print(f"Installed {display_name} profile: {result.profile}")
            if result.catalog is not None:
                print(f"Installed {display_name} catalog: {result.catalog}")
            if result.environment is not None:
                print(f"Stored local environment: {result.environment}")
            elif args.provider == BEDROCK_PROFILE_NAME:
                print("Authentication: AWS SDK credential chain")
            elif args.provider == FOUNDRY_PROFILE_NAME:
                print("Authentication: Microsoft Entra ID through Azure CLI")
            print(f"Desktop: codex-provider use {args.provider}")
            print(f"CLI: codex-provider run {args.provider}")
        elif args.command == "run":
            return run_codex(paths, args.profile, args.codex_args)
        elif args.command == "credential":
            print(
                read_environment(
                    paths.provider_environment(args.provider),
                    provider_environment_key(args.provider),
                )
            )
        elif args.command == "restore":
            snapshot = restore_original(paths)
            print("Restored the original provider selection.")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "default":
            snapshot = use_defaults(paths)
            print("Removed provider overrides. Codex defaults will apply.")
            print(f"Rollback snapshot: {snapshot}")
        elif args.command == "rollback":
            snapshot, provider = rollback(paths)
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
