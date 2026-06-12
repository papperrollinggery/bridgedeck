<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **bridgedeck** (1494 symbols, 3234 relationships, 69 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/bridgedeck/context` | Codebase overview, check index freshness |
| `gitnexus://repo/bridgedeck/clusters` | All functional areas |
| `gitnexus://repo/bridgedeck/processes` | All execution flows |
| `gitnexus://repo/bridgedeck/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

## BridgeDeck Safety Rules

BridgeDeck is a local configuration and token bridge for Codex.app, Claude clients, CC Switch, and AiMaMi. Treat OAuth tokens, account IDs, emails, local paths, logs, screenshots, and generated diagnostics as sensitive.

## Token Management Architecture (CRITICAL)

BridgeDeck shares the macOS machine with Codex.app and AiMaMi.app. These apps may use the same OpenAI OAuth client (`app_EMoamEEZ73f0CkXaXp7hrann`) and the same accounts. OpenAI refresh tokens rotate on use, so multiple apps refreshing the same stored token can cause `refresh_token_reused` failures.

Current token storage:

| App | Auth file | Refresh behavior |
|-----|-----------|------------------|
| Codex.app | `~/.codex/auth.json` and `~/.cc-switch/codex_oauth_auth.json` | Independent refresh |
| AiMaMi | `~/.codex/accounts/snapshots/*.json` | Independent refresh, writes token snapshots |
| BridgeDeck | `~/.cc-switch/bridgedeck-auth.json` | Snapshot-first, then own refresh fallback |

BridgeDeck token resolution order in `AuthStore.get_access_token()`:

1. In-memory `_token_cache` when the access token is still fresh.
2. AiMaMi/Codex snapshot from `~/.codex/accounts/snapshots/*__{account_id}.json`.
3. Own refresh through `~/.cc-switch/bridgedeck-auth.json` only as fallback.

Never:

- Change `AUTH_STORE_PATH` back to `~/.cc-switch/codex_oauth_auth.json`.
- Delete or ignore `~/.codex/accounts/snapshots/` when diagnosing token behavior.
- Run token refresh tests against real OpenAI endpoints; mock refresh calls.
- Publish raw auth stores, snapshots, logs, screenshots, or `.env` files.

If `refresh_token_reused` reappears, first check whether Codex.app or AiMaMi recently refreshed the same account, whether fresh snapshots exist under `~/.codex/accounts/snapshots/`, and bridge logs for `oauth_token` events.

## External Review Tools

Use Oracle or similar external review tools only for complex code review, architecture review, difficult bug diagnosis, or broad refactor risk analysis.

Before any real external review run:

- Run a dry-run/package summary first.
- Attach the smallest necessary reviewed file set.
- Exclude auth stores, `.env`, local logs, screenshots, generated diagnostics, account data, customer data, large binaries, and unrelated private files.
- Do not add Oracle MCP/global config without explicit user approval.
- Treat external model output as advisory only; verify against source, tests, docs, and runtime behavior before applying changes.

Allowed starting pattern:

```bash
npx -y @steipete/oracle --dry-run summary -p "<review task>" --file "<specific safe path>"
```

## Verification

Run relevant checks after changes:

```bash
python3 -m py_compile bridgedeck.py local_codex_bridge.py
python3 -m unittest discover -s tests
```
