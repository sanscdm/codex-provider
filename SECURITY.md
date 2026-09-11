# Security

## Report a vulnerability

Do not open a public issue for a credential leak or a configuration-write vulnerability. Use GitHub's private vulnerability reporting for this repository.

## Credential boundary

This project does not store provider credentials. Keep credentials in the provider's supported environment or credential manager.

Do not include any of these files in an issue or pull request:

- `~/.codex/config.toml`
- `~/.codex/.env`
- `~/.codex/auth.json`
- files under `~/.codex-provider`

Provider snapshots contain only selected top-level settings, but they can still reveal local model names and filesystem paths.

## Supported scope

Security fixes cover the latest released version on macOS and Linux.
