# BridgeDeck

Local account control panel for CC Switch, Codex OAuth accounts, Claude Code, Codex CLI, and OpenAI/Anthropic-compatible local API access.

Languages: [English](README.md) | [Simplified Chinese](README.zh-CN.md)

BridgeDeck is a local macOS helper. It does not host a cloud proxy, does not issue tokens, and does not copy OAuth tokens into generated Codex CLI profiles. It reads your local CC Switch and Codex configuration, then gives you a safer UI for account routing, bridge provider repair, local API setup, usage visibility, and diagnostics.

BridgeDeck is an independent project. It is not affiliated with CC Switch, OpenAI, Anthropic, GitHub, Microsoft, or any desktop client vendor. Bridge, OAuth, gateway, and account-routing workflows may be subject to the terms of the services you use.

## What It Solves

BridgeDeck is useful when one machine has multiple ChatGPT/Codex OAuth accounts and several tools need different entry points:

- Claude Code needs a Claude-compatible provider that actually routes to a selected Codex account.
- Codex CLI needs either a standalone per-account launcher or a global default account.
- Third-party tools need an OpenAI-compatible `base_url` and placeholder key.
- Claude Desktop or Anthropic-compatible clients need a local `/v1/messages` bridge.
- Account quota, provider binding, and actual token identity need to be checked without exposing real tokens.

## Main Capabilities

- **BridgeDeck-managed ChatGPT authorization**: generate an OpenAI device code in BridgeDeck, complete authorization in the browser, then join or update the matching CC Switch Local Bridge provider.
- **Claude Code bridge providers**: create, repair, and inspect Claude providers that route through `127.0.0.1:8876`.
- **Codex CLI routing**: generate launcher-only per-account Codex CLI commands and optionally set the global Codex CLI default.
- **OpenAI-compatible local API**: expose account-scoped `/v1/responses`, `/v1/chat/completions`, and `/v1/models`.
- **Anthropic-compatible local API**: expose `/v1/messages` for Claude-style clients.
- **Usage dashboard**: show request count, token totals, cache write tokens, cache hit tokens, cache miss tokens, hit rate, status, entry source, requested model, and actual routed model.
- **Account status checks**: compare CC Switch provider binding, actual OAuth identity, Claude config, Codex CLI config, and Desktop/global Codex state.
- **Privacy-first UI**: mask account IDs, emails, local paths, and tokens by default; require explicit local actions for write operations.

## Runtime Ports

| Port | Component | Purpose |
| --- | --- | --- |
| `8899` | BridgeDeck UI | Local web control panel |
| `8876` | Local Codex Bridge | Account-scoped OpenAI/Anthropic-compatible API |
| `15721` | CC Switch | Existing CC Switch service |

BridgeDeck binds to `127.0.0.1` by default.

## Install

### Download the macOS App

1. Download `BridgeDeck.dmg` from [GitHub Releases](https://github.com/papperrollinggery/bridgedeck/releases).
2. Open the DMG and drag `BridgeDeck.app` to `Applications`, or run it directly.
3. If macOS blocks the unsigned app, right-click the app and choose `Open`.

When the app icon is opened, BridgeDeck shows a native choice dialog:

- First launch: BridgeDeck suggests an install scan before opening the UI. The scan runs Python compile checks, package-script syntax checks, and `/Applications/BridgeDeck.app` freshness checks.
- `Open UI`: start or open the `8899` control panel.
- `Start Bridge Only`: start only the `8876` Local Codex Bridge.
- `Stop UI, Keep Bridge`: stop the `8899` UI while leaving `8876` running.

### Run From Source

```bash
chmod +x run-bridgedeck.command
./run-bridgedeck.command
```

Manual UI start:

```bash
python3 bridgedeck.py --host 127.0.0.1 --port 8899
```

Manual UI URL:

```text
http://127.0.0.1:8899
```

Run the same install scan manually:

```bash
python3 bridgedeck.py --install-scan
```

Start, stop, or inspect only the Local Codex Bridge:

```bash
python3 bridgedeck.py --local-bridge start
python3 bridgedeck.py --local-bridge status
python3 bridgedeck.py --local-bridge restart
python3 bridgedeck.py --local-bridge stop
```

## Common Workflows

### Authorize or Refresh a ChatGPT/Codex Account

1. Open BridgeDeck.
2. Go to `Entry Switching`.
3. Click `Generate Authorization Code`.
4. Open the displayed OpenAI device authorization page.
5. Enter the code and confirm authorization.
6. Return to BridgeDeck and wait for the status to complete.
7. Click `Join CC Switch` for a new account, or `Update CC Switch` for an existing account.

BridgeDeck stores only the refresh token in the CC Switch-compatible OAuth account store. It does not return the access token to the page.

### Refresh Quota After Reauthorization

After reauthorizing an account, click `Refresh quota` on the quota board or restart the Local Codex Bridge. BridgeDeck treats a newer `~/.cc-switch/bridgedeck-auth.json` as authoritative, invalidates older in-memory access tokens, and ignores Codex/AiMaMi account snapshots from `~/.codex/accounts/snapshots/` when those snapshots are older than the BridgeDeck auth store.

This is why an account can briefly show both `authorized` and `needs reauthorization`: the UI may have a fresh refresh token while the already running bridge process still has an old access token or an older snapshot. Refreshing quota now forces the bridge to re-check the newer auth store. If an account still shows `network_error` with an upstream `403` or HTML usage response, retry later or check the active proxy; that response is not always an invalid authorization.

### Route Claude Code Through a Selected ChatGPT Account

1. Make sure the target account exists in CC Switch or authorize it through BridgeDeck.
2. Open `Entry Switching`.
3. Select the account under `Claude Code`.
4. Apply the Claude Code account.
5. Confirm the status matrix shows the expected current account and no provider mismatch.

### Create a Standalone Codex CLI Launcher

Use this when one terminal or automation should use a specific account without changing the global default:

```text
~/.cc-switch/codex-cli-launchers/codex-<name>.command
```

Generated launchers route through the local bridge and do not copy OAuth tokens into `auth.json`.

### Set the Global Codex CLI Account

Use this only for tools that call the fixed `codex-current.command` path or tmux/OMC shims.

BridgeDeck does not change Codex Desktop's native `~/.codex/config.toml` for this action. It only updates the launcher/shim path and does not write `access_token`, `refresh_token`, or `id_token`.

### Temporary Codex Desktop Bridge Mode

Codex Desktop should stay native by default. If you need an emergency local bridge test, use the explicit temporary Bridge mode in the UI. It writes a marked `model_provider = "bridgedeck"` block with a backup and can be reverted with `Restore native`.

### Codex Native Proxy Repair

For Codex Desktop connection stalls, BridgeDeck can repair `~/.codex/.env` with HTTP/HTTPS/ALL/WS/WSS proxy variables. This does not change `~/.codex/config.toml`, model selection, reasoning effort, fast mode, or provider settings. Restart Codex Desktop after repairing.

## Local API Access

BridgeDeck exposes account-scoped local routes. The API key is a local placeholder, not a real OpenAI token.

```bash
OPENAI_API_KEY=sk-bridgedeck-local-placeholder
OPENAI_BASE_URL=http://127.0.0.1:8876/accounts/<account_id>/v1
```

Supported OpenAI-compatible routes:

```text
POST /accounts/<account_id>/v1/responses
POST /accounts/<account_id>/v1/chat/completions
GET  /accounts/<account_id>/v1/models
```

Supported Anthropic-compatible route:

```text
POST /accounts/<account_id>/v1/messages
```

Example Anthropic-style environment:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8876/accounts/<account_id>/v1
ANTHROPIC_AUTH_TOKEN=local-bridge
ANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark
ANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex
ANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5
CLAUDE_CODE_ATTRIBUTION_HEADER=0
CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000
```

Do not set `ANTHROPIC_MODEL` unless you intentionally want to force every main Claude Code request to one model. Leaving it unset keeps Claude's `haiku` / `sonnet` / `opus` slot routing meaningful.

BridgeDeck also exposes desktop-safe Claude-style model aliases so clients with model-name restrictions can route to the intended GPT model while the UI still shows both the requested model and actual routed model.

### Claude Code Attribution Header

Claude Code may inject a dynamic `x-anthropic-billing-header` into the system prompt for attribution/billing analytics. On official Anthropic endpoints this is usually harmless. On third-party, local, or proxy model routes, the dynamic `cch` value can break prompt-cache reuse and increase cost/latency. BridgeDeck can disable it by setting `CLAUDE_CODE_ATTRIBUTION_HEADER=0` and can strip the block at the proxy layer for non-official routes.

This does not affect Claude Code core functionality, model quality, or git commit attribution. Disable the optimization only if you intentionally need official attribution behavior.

## Usage Dashboard

The `Usage Details` page reads Local Codex Bridge state and shows:

- total requests
- total tokens
- input and output tokens
- cache creation/write tokens
- cache hit tokens
- cache miss tokens
- cache hit and miss rate
- provider/account label
- requested model and actual routed model
- client source, such as Codex, Claude Code, Desktop, Hermes, or generic API
- HTTP status and recent error state

Only recent local events are retained. Account identifiers are masked before display.

## Files Read or Written

BridgeDeck may read or write these local files depending on the action you choose:

```text
~/.cc-switch/cc-switch.db
~/.cc-switch/settings.json
~/.cc-switch/bridgedeck-auth.json
~/.cc-switch/codex-cli-launchers/*
~/.cc-switch/bridgedeck-backups/*
~/.cc-switch/bridgedeck-local-bridge-state.json
~/.codex/config.toml
~/.codex/.env
~/.codex/accounts/snapshots/*.json
~/.codex-cli-*
```

Backups are written before local configuration changes:

```text
~/.cc-switch/bridgedeck-backups/
```

## Security and Privacy

- Localhost binding is the default.
- Non-loopback binding requires `--allow-remote`.
- Remote mode is read-only by default.
- Remote read-only responses redact account IDs, emails, local paths, proxy credentials, and bridge account URLs.
- Write APIs and token reveal in remote mode require `--allow-remote-write`.
- API requests require a per-run browser token.
- Cross-site Fetch Metadata is rejected where supported by the browser.
- HTML responses use CSP, frame blocking, `no-store`, `nosniff`, and referrer policy headers.
- Full tokens are not returned by `/api/data` unless the local UI explicitly requests secret reveal.

Never publish these files or raw screenshots from a real machine:

```text
~/.cc-switch/bridgedeck-auth.json
~/.cc-switch/cc-switch.db
~/.cc-switch/bridgedeck-local-bridge-state.json
~/.codex/auth.json
~/.codex/accounts/snapshots/*.json
~/.codex-cli-*/auth.json
screenshots with account IDs or emails
logs containing tokens, account IDs, emails, local paths, or proxy credentials
```

## Troubleshooting

| Problem | Check |
| --- | --- |
| UI keeps loading | Open `http://127.0.0.1:8899`, then restart only the UI if needed. The `8876` bridge can keep running. |
| Local API returns `404` | Use `/accounts/<account_id>/v1` as the base URL and make sure the route is one of the supported local routes. |
| Local API returns `401` | Re-authorize the account in BridgeDeck or CC Switch, then update the matching Local Bridge provider. |
| Proxy returns `503` | Check the active proxy, CC Switch service, and Local Codex Bridge status. Temporary upstream service errors can also appear as `503`. |
| Desktop client rejects model names | Use the model aliases shown by BridgeDeck and confirm the UI displays the actual routed model. |
| Quota/account mismatch | Use the status matrix and provider mismatch panel, then re-authorize or update the provider binding. |
| Quota does not update after reauthorization | Click `Refresh quota` or restart the Local Codex Bridge so the running bridge reloads the newer `bridgedeck-auth.json`; reopen BridgeDeck after upgrading the app. |

## CLI Options

```text
--db PATH              path to cc-switch.db
--settings PATH        path to settings.json
--auth-store PATH      path to bridgedeck-auth.json
--host HOST            listen host, default 127.0.0.1
--port PORT            listen port, default 8899
--allow-remote         allow non-loopback bind; read-only and no secret reveal
--allow-remote-write   allow write APIs and token reveal in remote mode
--local-bridge ACTION  start/stop/restart/status 8876 without starting the UI
```

## Development

Run the local checks:

```bash
python3 -m py_compile bridgedeck.py local_codex_bridge.py
python3 -m unittest discover -s tests
zsh -n run-bridgedeck.command
zsh -n package-bridgedeck-dmg.command
```

Package the macOS app and DMG:

```bash
chmod +x package-bridgedeck-dmg.command
./package-bridgedeck-dmg.command
shasum -a 256 dist/BridgeDeck.dmg
```

The package script always runs `py_compile` and shell syntax checks before building. Set `BRIDGEDECK_PACKAGE_TESTS=1` to include the full unit test suite in the package preflight.

Project layout:

```text
bridgedeck.py                   local web app and API
local_codex_bridge.py           8876 account-scoped bridge service
BridgeDeckLauncher.swift        native macOS app launcher
run-bridgedeck.command          source launcher
package-bridgedeck-dmg.command  macOS app and DMG packager
README.md                       English documentation
README.zh-CN.md                 Simplified Chinese documentation
SECURITY.md                     security policy
CONTRIBUTING.md                 contribution guide
CHANGELOG.md                    changelog
OPEN_SOURCE_CHECKLIST.md        release checklist
LICENSE                         PolyForm Noncommercial 1.0.0
COMMERCIAL.md                   commercial licensing notes
```

## License

BridgeDeck is licensed under the PolyForm Noncommercial License 1.0.0.

Commercial use requires a separate written commercial license. See `COMMERCIAL.md`.
