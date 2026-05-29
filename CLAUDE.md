<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **bridgedeck** (1364 symbols, 2912 relationships, 64 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Token Management Architecture (CRITICAL)

**Background:** BridgeDeck shares the macOS machine with Codex.app and AiMaMi.app. All three apps use the same OpenAI OAuth client (`app_EMoamEEZ73f0CkXaXp7hrann`) and manage tokens for the same accounts. OpenAI refresh tokens are **single-use** (rotation) — once used, the old token is immediately invalidated.

**Problem (resolved):** Previously all three apps shared `~/.cc-switch/codex_oauth_auth.json`, causing a race condition where one app's refresh would invalidate the other's token → `refresh_token_reused` errors.

**Current architecture:**

| App | Auth file | Refresh behavior |
|-----|-----------|-----------------|
| Codex.app | `~/.codex/auth.json` + `~/.cc-switch/codex_oauth_auth.json` | Independent refresh |
| AiMaMi | `~/.codex/accounts/snapshots/*.json` | Independent refresh, writes to snapshots |
| BridgeDeck | `~/.cc-switch/bridgedeck-auth.json` | **Snapshot-first**: reads AiMaMi snapshots before refreshing |

**BridgeDeck token resolution order** (`get_access_token` in `local_codex_bridge.py`):
1. In-memory cache (`_token_cache`) — if not expiring soon, use directly
2. AiMaMi snapshot (`~/.codex/accounts/snapshots/*__{account_id}.json`) — if access_token exists and not expired, use it (zero refresh, no token consumption)
3. Own refresh via `bridgedeck-auth.json` — fallback only

**NEVER DO:**
- NEVER change `AUTH_STORE_PATH` back to `codex_oauth_auth.json` — this causes the multi-app race condition
- NEVER delete `~/.codex/accounts/snapshots/` — BridgeDeck depends on AiMaMi's token snapshots
- NEVER run token refresh in tests against real OpenAI endpoints — mock the `_refresh_token` method

**If `refresh_token_reused` errors reappear:**
1. Check if Codex.app or AiMaMi also refreshed the same account recently
2. Check if `CODEX_SNAPSHOT_DIR` (`~/.codex/accounts/snapshots/`) exists and has fresh snapshots
3. Check bridge log for `oauth_token` entries — count how many refreshes happened
4. Consider separating accounts: assign some to AiMaMi only, others to BridgeDeck only

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