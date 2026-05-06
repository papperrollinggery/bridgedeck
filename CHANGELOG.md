# Changelog

## 0.2.17

- Added Local Codex Bridge silent stream idle timeout handling: long upstream silence now ends with a `response.failed` event instead of hanging forever.
- Added per-stream end diagnostics with request id, model, effort, upstream events, downstream writes, heartbeat count, client disconnect state, terminal event state, and idle timeout state.
- Kept reasoning heartbeats non-polluting by default; no fake `response.output_text.delta` is emitted unless legacy visible mode is explicitly enabled.

## 0.2.16

- Fixed Local Codex Bridge reasoning visibility so encrypted reasoning heartbeats no longer pollute assistant output text.
- Preserved OpenAI Responses reasoning summaries while keeping encrypted reasoning content for multi-turn continuity.
- Added reasoning summary defaults and safe effort normalization for GPT-5.4.
- Added safe Claude common config extraction so hooks/plugins can sync without leaking provider token, model, or context settings.
- Scoped Claude context sizing and model env to individual providers instead of common config.

## 0.2.15

- Stabilized Local Codex Bridge streaming failures so started SSE responses close with stream terminal events instead of JSON 500 responses.
- Kept Claude Code compatibility placeholder deltas while adding bridge stream error diagnostics.
- Added automatic Claude plugin enablement sync between installed plugins, `~/.claude/settings.json`, and `~/.ccswitch-common-config.json`.
- Added global Codex CLI fixed launcher and OMC/tmux shim status so provider switches do not change the managed Codex entry point.
- Fixed account status tables to use actual Desktop, launcher, and provider-route accounts instead of stale `~/.codex/auth.json` or empty provider binding fields.

## 0.2.14

- Added provider-level Claude Code auto-compact controls, including 220k and 1m context window presets.
- Added a one-click sync for common provider env values across Local Codex Bridge providers while preserving account-specific URL/token fields.
- Added safe duplicate Local Codex Bridge provider cleanup with preview, current-provider handoff, and DB/settings backups.
- Fixed the Global Codex CLI selector so refresh reflects the actual `~/.codex/config.toml` account instead of falling back to the first account.
- Added per-tool actual-account status lines and refresh buttons to the daily account selector.
- Added visible refresh feedback so status buttons show a busy state and completion time.

## 0.2.13

- Fixed the macOS launcher so clicking BridgeDeck in the Dock reopens the browser page while keeping the web server in the background.

## 0.2.12

- Restored frequent encrypted reasoning placeholder deltas for Claude Code compatibility.
- Added reasoning heartbeat deltas during long silent reasoning windows.
- Made Local Codex Bridge startup prefer a Python runtime that can import `httpx`.
- Fixed the local LaunchAgent runtime path after Homebrew Python moved.

## 0.2.8

- Bundled the managed Local Codex Bridge script with BridgeDeck.
- Prefer the bundled bridge script for service start/restart.

## 0.2.7

- Redacted service process details, local paths, and upstream proxy values in remote read-only mode.
- Masked proxy credentials in local service status responses.

## 0.2.6

- Forced local quota requests to bypass system proxies.
- Added Local Codex Bridge service status, start, stop, restart, and quota repair controls.
- Made the macOS app a background helper so it does not stay bouncing in the Dock.

## 0.2.5

- Split the daily UI into Claude Code, standalone Codex CLI, and global Codex CLI account selectors.
- Renamed the default Codex workflow to global Codex CLI to clarify when `~/.codex/config.toml` is changed.
- Added an actual Claude Code provider status line so CC Switch changes are visible without changing the selected account dropdown.
- Made the macOS command and app launcher idempotent: if BridgeDeck is already running, they only open the page.
- Fixed Local Codex Bridge provider metadata so CC Switch forwards Claude requests to the local bridge while keeping Codex account quota visible.
- Added a BridgeDeck OpenAI quota board and optional auto-switch mode with Plus -> Pro -> Pro 20x priority. Auto-switch only runs while the current target is Local Codex Bridge, so third-party CC Switch providers are left alone.
- Improved auto-switch to rank accounts by live quota plan data and create a missing Local Codex Bridge provider for newly authorized OpenAI accounts, without touching third-party providers.

## 0.2.4

- Made Codex CLI switching explicit by showing CODEX_HOME startup commands for each detected CLI profile.
- Renamed the CLI workflow from isolated account creation to CLI switching.

## 0.2.3

- Added CSP nonce, frame blocking, and additional browser security headers.
- Added Fetch Metadata rejection for cross-site API requests.
- Redacted account identifiers, emails, local paths, and bridge URLs server-side in remote read-only mode.

## 0.2.2

- Replaced boolean provider states with Chinese labels.
- Added automatic diagnosis advice for account/provider/CLI status.
- Masked email addresses, account IDs, and home paths in the UI to make screenshots safer.

## 0.2.1

- Simplified the first screen with status tiles, recommended next action, and direct workflow buttons.
- Moved lower-frequency provider repair and logs into advanced sections.

## 0.2.0

- Added automated security tests for Host, Origin, CSRF, remote read-only mode, secret reveal, and request size handling.
- Added task-oriented UI layout with contextual guide panel.
- Added Codex CLI isolated account workflow.
- Added token reveal control; full tokens are hidden by default.
- Added provider/token mismatch detection.
- Added local-only bind protection and request size guard.
- Added per-run API token, Host/Origin checks, and read-only remote mode.
- Added atomic JSON writes and dedicated backup directory.
- Restricted isolated CLI profiles to `~/.codex-cli-*`.
- Added README, SECURITY, CONTRIBUTING, LICENSE, and packaging docs.

## 0.1.0

- Initial local bridge provider helper.
