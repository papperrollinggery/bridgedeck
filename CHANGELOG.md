# Changelog

## 0.2.11

- Distinguished transport stream closure from actual Responses API terminal events.
- Logged SSE terminal event, last event, response status, delta count, and reasoning item count for Claude Code GPT streams.

## 0.2.10

- Added Local Codex Bridge stream completion diagnostics for completed, client-disconnected, and upstream-error streams.

## 0.2.9

- Stopped mutating streaming Responses SSE in the local bridge.
- Logged the selected model and reasoning effort server-side only.
- Fixed Claude Code GPT streams stopping early after the bridge inserted visible model hints.

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
