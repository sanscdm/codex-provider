# codex-provider

`codex-provider` switches the model provider used by new Codex desktop tasks without replacing unrelated Codex settings.

It keeps native Codex profiles as the configuration source. It stores selection-only recovery snapshots in `~/.codex-provider`. Snapshots do not copy provider definitions, MCP configuration, or credentials.

## Status

This is a small alpha release for macOS and Linux. The desktop launcher is macOS-only.

## Requirements

- Python 3.9 or newer
- Codex CLI
- macOS for the optional desktop launcher

Optional provider tools:

- AWS CLI for Bedrock SSO login
- Azure CLI for Microsoft Foundry Entra ID authentication

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
# Or: uv tool install --force .
```

## Quick start

Install OpenRouter end to end:

```bash
codex-provider install openrouter
```

The command uses `OPENROUTER_API_KEY` when it is already present, then checks the existing local provider environment. Otherwise, it asks for the API key without echoing it. It installs the selection profile, adds the provider definition, captures the original selection, and stores the key only in `~/.codex-provider/providers/openrouter.env` with mode `0600`. This is a plaintext local environment file. Do not share or commit it.

Providers installed by this tool use Codex command-backed authentication. Codex asks `codex-provider` for the stored credential when it starts a request. The key does not need to be exported into the terminal or macOS login environment.

Apply it to new desktop tasks:

```bash
codex-provider use openrouter
```

Fully quit and reopen Codex. For the CLI, run:

```bash
codex-provider run openrouter
```

`run` reads only the selection values from the profile and passes them as temporary Codex configuration overrides. It does not select the profile file as Codex's writable permission layer. Pass Codex arguments after `--`, for example:

```bash
codex-provider run openrouter -- --ephemeral
```

After `use openrouter`, the base configuration selects OpenRouter. Command-backed authentication lets the native CLI resume without sourcing an environment file:

```bash
codex resume
```

Do not run `codex --profile openrouter`. Codex can save tool approval changes into the selected profile file. A provider selection profile must stay selection-only. Use `codex-provider run openrouter` or apply it with `codex-provider use openrouter` and then run `codex` normally.

For a provider that you configure manually:

1. Put custom provider definitions in `~/.codex/config.toml`.
2. Put each selection profile in `~/.codex/<name>.config.toml`.
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

Open `Codex Provider Switcher` from `~/Applications`. Choose a selection profile, the original selection, Codex defaults, or rollback.

The app does not restart Codex because that could interrupt an active task. Fully quit and reopen Codex after a switch.

## Codex selection profiles

The temporary CLI path does not change `~/.codex/config.toml`:

```bash
codex-provider run deepseek
codex --model gpt-6-astra -c 'model_reasoning_effort="high"'
```

The desktop app does not currently select a profile at launch. `codex-provider use <name>` copies only the profile's supported top-level selection values into a marked block in the base configuration.

Provider definitions remain in the base config. This lets the tool switch selections without duplicating authentication settings.

## Example: DeepSeek

DeepSeek needs a model catalog because its models are not in the standard Codex catalog. The installer extracts that catalog from DeepSeek's official setup script after verifying the script's pinned SHA-256 checksum. It does not execute the downloaded script.

Choose DeepSeek V4 Pro during installation:

```bash
codex-provider install deepseek --model deepseek-v4-pro
```

The installer is the supported setup path because it writes the local credential file and records the installed `codex-provider` command path. The files in [`examples`](examples) are references for review; they do not contain credentials.

The installed selection profile has this shape:

```bash
cat examples/profiles/deepseek.config.toml
```

The example uses `./deepseek.models.json`. Codex resolves this relative path from the user configuration directory. The catalog is generated on the local machine and is not committed.

CLI:

```bash
codex-provider run deepseek
```

Desktop selection:

```bash
codex-provider use deepseek
```

## Example: OpenRouter

The default model is OpenRouter's `~openai/gpt-latest` alias:

```bash
codex-provider install openrouter
codex-provider use openrouter
```

Choose an exact OpenRouter model slug during installation when you need a fixed model:

```bash
codex-provider install openrouter --model openai/gpt-5.6-sol
```

OpenRouter provides model metadata to Codex after command-backed authentication. The installer does not create a local model catalog. This avoids a stale second copy of OpenRouter's changing model list.

CLI without changing the desktop selection:

```bash
codex-provider run openrouter
```

After a desktop switch, fully quit and reopen Codex. Existing tasks keep the provider that they started with.

## Example: Amazon Bedrock

Install the built-in Codex Bedrock provider with an AWS profile and Region:

```bash
codex-provider install bedrock \
  --model openai.gpt-5.6-sol \
  --region us-east-2 \
  --aws-profile codex-bedrock
aws sso login --profile codex-bedrock
codex-provider use bedrock
```

Fully quit and reopen Codex. The installer does not copy AWS credentials. Codex uses its built-in `amazon-bedrock` provider and the standard AWS credential chain.

For a temporary CLI session without changing the desktop selection:

```bash
codex-provider run bedrock
```

Omit `--aws-profile` to use the default AWS credential chain. The model and Region must be enabled for the company's AWS account. See the [official Codex Bedrock guide](https://learn.chatgpt.com/docs/amazon-bedrock).

## Example: Microsoft Foundry

The supported path is a Microsoft Foundry deployment with an OpenAI-compatible Responses endpoint. The `--model` value is the deployment name.

Use Microsoft Entra ID by default:

```bash
az login
codex-provider install foundry \
  --endpoint https://YOUR_RESOURCE.services.ai.azure.com/openai/v1 \
  --model coding-production
codex-provider use foundry
```

The installer records the resolved Azure CLI path. Codex asks Azure CLI for a short-lived token when needed. No Azure token is stored by `codex-provider`.

API-key authentication is also available:

```bash
codex-provider install foundry \
  --endpoint https://YOUR_RESOURCE.openai.azure.com/openai/v1 \
  --model coding-production \
  --auth api-key
```

The command reads `AZURE_OPENAI_API_KEY` when set. Otherwise, it asks without echoing the value. It stores the key only in `~/.codex-provider/providers/foundry.env` with mode `0600`.

For a temporary CLI session:

```bash
codex-provider run foundry
```

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
codex-provider install openrouter [--model MODEL]
codex-provider install bedrock [--model MODEL] [--region REGION] [--aws-profile PROFILE]
codex-provider install foundry --endpoint URL --model DEPLOYMENT [--auth entra|api-key]
codex-provider run PROFILE [-- CODEX_ARGS...]
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
- Provider keys are written only to local mode-`0600` environment files.
- Bedrock uses the built-in AWS credential chain. The installer does not copy AWS credentials.
- Foundry endpoints must use HTTPS and an official Azure OpenAI or Microsoft Foundry hostname.
- Foundry Entra ID authentication stores no token. Azure CLI owns login and refresh.
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
