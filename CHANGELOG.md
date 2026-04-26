# Changelog

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
