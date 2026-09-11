# codex-provider

`codex-provider` switches the model provider used by new Codex desktop tasks without replacing unrelated Codex settings.

It keeps native Codex profiles as the configuration source. It stores selection-only recovery snapshots in `~/.codex-provider`. Snapshots do not copy provider definitions, MCP configuration, or credentials.

## Status

This is a small alpha release for macOS and Linux. The desktop launcher is macOS-only.

## Requirements

- Python 3.9 or newer
- Codex CLI
- macOS for the optional desktop launcher

## Install from a checkout

With `pipx`:

```bash
pipx install .
```

Or with `uv`:

```bash
uv tool install .
```

Upgrade after pulling changes:

```bash
pipx install . --force
```

## Quick start

Install DeepSeek end to end:

```bash
codex-provider install deepseek
```

The command uses `DEEPSEEK_API_KEY` when it is already present. Otherwise, it asks for the API key without echoing it. It downloads the pinned official DeepSeek catalog, installs the native profile, adds the provider definition, captures the original selection, and stores the key only in `~/.codex-provider/providers/deepseek.env` with mode `0600`. This is a plaintext local environment file. Do not share or commit it.

Apply it to new desktop tasks:

```bash
codex-provider use deepseek
```

Fully quit and reopen Codex. For the native CLI, load the same local environment first:

```bash
source ~/.codex-provider/providers/deepseek.env
codex --profile deepseek
```

On macOS, `use deepseek` publishes the variable to the current login session so the restarted desktop app can read it. Switching to another profile, restoring the original selection, or using defaults clears it from the login session.

For a provider that you configure manually:

1. Put custom provider definitions in `~/.codex/config.toml`.
2. Put each native profile in `~/.codex/<name>.config.toml`.
3. Capture your current provider selection once:

```bash
codex-provider init
```

4. List and apply profiles:

```bash
codex-provider list
codex-provider use deepseek
```

5. Fully quit and reopen Codex. Start a new task.

Restore the selection captured by `init`:

```bash
codex-provider restore
```

Use Codex defaults, with no top-level provider override:

```bash
codex-provider default
```

Undo the last switch:

```bash
codex-provider rollback
```

## macOS desktop switcher

Install the small chooser app:

```bash
codex-provider desktop-install
```

Open `Codex Provider Switcher` from `~/Applications`. Choose a native profile, the original selection, Codex defaults, or rollback.

The app does not restart Codex because that could interrupt an active task. Fully quit and reopen Codex after a switch.

## Native Codex profiles

The native CLI path does not change `~/.codex/config.toml`:

```bash
codex --profile deepseek
codex --profile openai --model gpt-6-astra -c 'model_reasoning_effort="high"'
```

The desktop app does not currently select a native profile at launch. `codex-provider use <name>` copies only the profile's supported top-level selection values into a marked block in the base configuration.

Provider definitions remain in the base config. This lets the tool switch selections without duplicating authentication settings.

## Example: DeepSeek

DeepSeek needs a model catalog because its models are not in the standard Codex catalog. The installer extracts that catalog from DeepSeek's official setup script after verifying the script's pinned SHA-256 checksum. It does not execute the downloaded script.

Choose DeepSeek V4 Pro during installation:

```bash
codex-provider install deepseek --model deepseek-v4-pro
```

For manual setup, add the provider definition from [`examples/base-config.toml`](examples/base-config.toml) to `~/.codex/config.toml`. Set `DEEPSEEK_API_KEY` only in your shell or local Codex environment. Never put it in a profile or this repository.

Copy the example profile:

```bash
cp examples/profiles/deepseek.config.toml ~/.codex/deepseek.config.toml
```

The example uses `./deepseek.models.json`. Codex resolves this relative path from the user configuration directory. The catalog is generated on the local machine and is not committed.

Native CLI:

```bash
codex --profile deepseek
```

Desktop selection:

```bash
codex-provider use deepseek
```

## Example: Amazon Bedrock

Use AWS SSO or another standard AWS credential source. Add the Bedrock AWS settings from [`examples/base-config.toml`](examples/base-config.toml) to the base Codex config.

```bash
aws sso login --profile codex-bedrock
cp examples/profiles/bedrock.config.toml ~/.codex/bedrock.config.toml
codex --profile bedrock
```

For desktop use:

```bash
codex-provider use bedrock
```

The model and Region must be enabled for the company's AWS account. See the [official Codex Bedrock guide](https://learn.chatgpt.com/docs/amazon-bedrock).

## Recovery model

`codex-provider` manages only these top-level keys:

```text
model
model_provider
model_catalog_json
model_reasoning_effort
model_reasoning_summary
model_verbosity
service_tier
web_search
oss_provider
openai_base_url
```

Before every switch, it writes those current values to `~/.codex-provider/snapshots`. `restore` uses the immutable first snapshot. `rollback` consumes the newest history entry.

If an older switcher already changed your config, initialize from a trusted earlier copy:

```bash
codex-provider init --original-config path/to/known-good-config.toml
```

This reads only the managed selection values from that file. It does not copy its provider tables or credentials.

## Commands

```text
codex-provider init [--original-config FILE]
codex-provider install deepseek [--model MODEL]
codex-provider list
codex-provider status
codex-provider use PROFILE
codex-provider restore
codex-provider default
codex-provider rollback
codex-provider desktop-install
```

## Security behavior

- Provider names are limited to letters, numbers, hyphens, and underscores.
- Custom providers must already exist in the base Codex config.
- Writes are atomic and use mode `0600`.
- A process lock prevents concurrent switches.
- Snapshots contain only provider selection values.
- Invalid TOML stops the switch before the Codex config changes.
- No credential, token, API key, or complete Codex configuration is copied.
- DeepSeek keys are written only to a local mode-`0600` environment file.
- DeepSeek catalog downloads use HTTPS, an allowed host, a size limit, a pinned checksum, strict JSON parsing, and an exact model allowlist.

## Development

Run all checks:

```bash
make check
```

The tests use temporary directories. They do not read or change the developer's real Codex configuration.

For isolated automation, set `CODEX_HOME` and `CODEX_PROVIDER_HOME` to temporary directories. Do not set these variables for normal use.

## License

MIT. See [`LICENSE`](LICENSE).
