# GStack Office Hours: Codex Stream Recurrence Plan

Date: 2026-05-24
Branch: `codex/gstack-office-hours-plan`
Scope: BridgeDeck product/design plan plus Milestone 1 implementation in the Codex-visible worktree.

## Execution Update

Milestone 1 plus Council hardening is implemented in this branch.

Changed:
- Added a read-only Codex Desktop Sentry app-state reader for `scope_v3.json`.
- Added `desktop_app_state` to Codex Desktop Doctor checks.
- Classified stale Desktop stream ownership as `desktop_stream_state_stale`.
- Changed the stale-stream action to `run_stability_route_canary`.
- Added app-state freshness checks so old Sentry evidence cannot directly trigger route changes.
- Added `stability_route_canary` output with guarded preconditions and pass criteria.
- Renamed the visible Bridge route wording to `Stability Route`.
- Kept active Stability Route in canary mode when stale stream evidence is still present.
- Kept restart-oriented advice out of the stale-stream recommendation path.
- Added public-health redaction for the Sentry scope path.
- Added unit coverage for stale app-state parsing, stale evidence freshness, Doctor routing priority, and active Stability Route canary state.

Verified:
- `python3 -m py_compile bridgedeck.py tests/test_security.py`
- `python3 -m unittest tests.test_security.CodexDesktopDoctorCase.test_codex_desktop_app_state_detects_stale_streaming_without_runtime tests.test_security.CodexDesktopDoctorCase.test_doctor_classifies_stale_streaming_state_as_http_bridge_route tests.test_security.CodexDesktopDoctorCase.test_doctor_prefers_stale_process_before_upstream_warning tests.test_security.CodexDesktopDoctorCase.test_doctor_classifies_clean_config_deprecation_as_upstream_warning tests.test_security.CodexDesktopDoctorCase.test_codex_desktop_doctor_endpoint_returns_status tests.test_security.CodexDesktopDoctorCase.test_public_health_is_loopback_only_and_redacted_without_csrf`
- `python3 -m unittest tests.test_security.CodexDesktopDoctorCase.test_codex_desktop_app_state_marks_old_stale_evidence_unfresh tests.test_security.CodexDesktopDoctorCase.test_doctor_requires_fresh_app_state_before_canary tests.test_security.CodexDesktopDoctorCase.test_doctor_keeps_active_stability_route_in_canary_mode_for_stale_stream tests.test_security.CodexDesktopDoctorCase.test_codex_desktop_mode_endpoints_require_explicit_post tests.test_security.CodexDesktopDoctorCase.test_daily_ui_has_separate_account_selectors`
- `python3 -m unittest tests.test_security`
- Live read-only Doctor check on this machine returned `desktop_stream_state_stale` with action `run_stability_route_canary`; `stability_route_canary` returned `ready_to_enable` / `enable_http_bridge_mode`.

Next plan:
- Milestone 2 should run the actual canary: enable Stability Route, execute one real streaming task, then compare fresh app-state before and after.
- Milestone 3 should add provider capability matrix storage and request shaping.
- Milestone 4 should add provider/account circuit breakers.

## Live Canary Receipt

Run time: 2026-05-24 13:23 Asia/Shanghai

Actions:
- Selected BridgeDeck account `7e517757-60eb-4e9d-8e3a-1ad7d6731dea`, matching the current global Codex launcher and recent successful local bridge stream.
- Enabled Codex Desktop Stability Route in `~/.codex/config.toml`.
- Wrote `model_provider = "bridgedeck"` and `supports_websockets = false`.
- Removed static Desktop `model` and `model_reasoning_effort` keys from the active config.

Backup:
- `/Users/jinjungao/.cc-switch/bridgedeck-backups/Users_jinjungao_.codex_config.toml.toolbak-codex-desktop-bridge-mode-20260524-132317-1779600197564871000-389efcb7`

Verification:
- `GET http://127.0.0.1:8876/accounts/7e517757-60eb-4e9d-8e3a-1ad7d6731dea/v1/models` returned models.
- Real SSE canary through local bridge returned `response.completed`, `terminal_event_seen=true`, duration `1.927s`, output tail `OK`.
- Doctor after canary returned `stability_route_canary_active` / `run_canary_stream`.
- Local bridge health latest stream: `completed_response_status=completed`, `terminal_event_seen=true`, `idle_timeout_seen=false`.
- `python3 -m unittest tests.test_security.LocalCodexBridgeCase` returned 80 tests OK before and after enabling.

Remaining observation:
- Codex Desktop Sentry app-state still shows stale owners from the existing Desktop runtime: `stale_stream_count=17`.
- The count moved from 16 to 17 while the existing Desktop runtime was still active, then stayed stable for a 30 second observation window after the local HTTP/SSE canary.
- This validates the HTTP/SSE Stability Route path, but a user-facing Codex Desktop turn should still be observed to confirm the Desktop process is reading the new config.
- The primary Codex Desktop app-server started before the config change, so any current in-flight Desktop session may still be using old in-memory state until that runtime reloads config.

Restore path:
- Run `BridgeManager.restore_codex_desktop_native_mode()` or use the UI action `恢复原生/清理静态项`.
- Keep the backup path above as the exact pre-canary config snapshot.

## Decision

Stop treating recurring Codex Desktop `websocket closed by server before response.completed` as a restart problem.

BridgeDeck should make this class of failure observable, routeable, and recoverable without depending on manual app restarts. The narrow wedge is a Codex Stream Stability Gate that detects stale Desktop stream state, validates proxy/router integrity, and can route affected sessions through a BridgeDeck-managed non-WebSocket path.

## Office Hours Diagnosis

### Demand Reality

The pain is real. The failure has repeated across restarts, interrupts active work, and forces manual diagnosis. The user is not asking for a nicer explanation; they are asking for a system that prevents recurrence.

Strongest evidence:
- Codex shows `stream disconnected before completion: websocket closed by server before response.completed`.
- Local Sentry state showed streaming owners without active runtimes.
- BridgeDeck and Hermes were healthy while Codex Desktop still reported stream failure.
- The user explicitly rejected more restart advice after repeated recurrence.

Conclusion: this is a state and routing reliability problem, not a user-education problem.

### Status Quo

Current workaround:
- Inspect logs manually.
- Check BridgeDeck health manually.
- Check proxy ownership manually.
- Restart Codex or related processes.
- Retry the interrupted turn.

Cost:
- Active work gets lost or delayed.
- The same diagnosis is repeated.
- Root causes remain mixed together: upstream WebSocket, local proxy, stale Desktop runtime, stale config, and BridgeDeck stream state.

The real competitor is not another tool. The real competitor is the user's ad hoc recovery routine.

### Desperate Specificity

Primary user: a local power user running Codex Desktop, BridgeDeck, Shadowrocket, Hermes, and multiple model/account routing layers on one macOS machine.

What gets them angry:
- A long Codex turn fails after several reconnects.
- The local bridge is healthy, but Desktop still wedges.
- The answer is "restart" after they already restarted.

What they need:
- A deterministic answer: which layer is broken.
- A one-action path that avoids the broken layer.
- A guard that blocks known-bad states before a long turn starts.

### Narrowest Wedge

Build one product surface:

`Codex Stream Stability Gate`

It should answer four questions before and during a Codex session:
1. Is Codex Desktop currently using a WebSocket path?
2. Is the Desktop stream state already stale?
3. Is the configured proxy path consistent and long-connection capable?
4. Should BridgeDeck route this session through non-WebSocket HTTP/SSE bridge mode?

This is smaller than a full router rewrite. It uses existing BridgeDeck pieces:
- `codex_desktop_doctor()`
- `proxy_diagnosis()`
- `bridge_stream_diagnostics()`
- Local Bridge `/v1/responses`
- Existing Stability Route config with `supports_websockets = false`

### Observation And Surprise

The surprising signal is not that WebSocket can fail. The surprising signal is that Codex Desktop can keep stale `streaming` ownership without an active runtime while BridgeDeck remains healthy.

That means BridgeDeck should not only watch its own local bridge logs. It must also inspect Codex Desktop app-state signals:
- `thread_count_streaming_without_active_runtime`
- `thread_count_streaming_owner`
- `pending_request_count`
- `inflight_turn_count`
- `host_child_app_server_process_count`
- recent `maybe_resume_success` or stale marked-streaming breadcrumbs

### Future Fit

This product becomes more essential as Codex gains more transport modes, background goals, app-server runtimes, plugins, and long-running turns.

The future problem is not "one request failed." The future problem is "which runtime owns this turn, which transport is active, and which layer should recover it?" BridgeDeck should become the local control plane for that answer.

## Premises

1. Recurring `response.completed` WebSocket failures should be classified as transport/state failures until proven otherwise.
2. Restarting is an acceptable emergency action, but not a durable product answer.
3. BridgeDeck should prefer routing around a known-bad transport over repeatedly repairing the same Desktop session state.
4. Capability declarations must be dynamic. Static claims like image/search/tool/websocket support can create false failures when upstream or proxy layers do not support them.
5. The first useful wedge is detection plus deterministic routing, not a full rewrite of Codex Desktop behavior.

## AiMaMi-Derived Product Lessons

### 1. Capability Declaration Must Be A Product Feature

AiMaMi v1.0.1 fixed Claude protocol model capability declaration. AiMaMi 1.0.6 added Image declaration compatibility.

BridgeDeck implication:
- Add a provider capability matrix.
- Track support for `websocket`, `image`, `web_search`, `tools`, `reasoning_effort`, and `reasoning_summary`.
- Let each provider/account override advertised capabilities.
- If upstream rejects image/search/tool calls, mark that capability degraded and retry the plain text path.

### 2. Router State Needs Cleanup, Not Just Diagnostics

AiMaMi includes startup cleanup, orphan provider cleanup, thread rollback, stale config detection, and managed block rewrite.

BridgeDeck implication:
- Add a Codex Desktop state integrity check.
- Detect stale model providers, stale managed blocks, orphan thread provider ids, and rollout/session metadata that points to removed providers.
- The repair action should be precise: rewrite only BridgeDeck-managed blocks and only known orphan thread/provider metadata.

### 3. Proxy Port Selection Must Be Verified Against Reality

AiMaMi FAQ explicitly calls out wrong proxy port detection as a cause of official model failures.

BridgeDeck implication:
- Compare `.env` proxy values, `launchctl getenv`, active port listeners, and live outbound connection owner.
- Report mismatches as blocking, not advisory.
- Validate the actual Codex process path, not only the shell environment.

### 4. Circuit Breakers Beat Repeated Retry

AiMaMi binary contains relay-provider circuit breaker strings such as `circuit open until`.

BridgeDeck implication:
- Add account/provider circuit breakers for repeated TLS EOF, 403, upstream stream error, and terminal-event missing failures.
- Temporarily remove unhealthy providers from automatic routing.
- Surface the expiry and reason in UI and health endpoints.

### 5. Recovery Must Be Mode-Based

AiMaMi exposes maintenance actions: reset config, system diagnosis, image compatibility, target mode repair.

BridgeDeck implication:
- Replace vague Doctor recommendations with mode-specific actions:
  - `enable_http_bridge_mode`
  - `repair_proxy_env`
  - `disable_websocket_transport`
  - `repair_capability_matrix`
  - `quarantine_provider`
  - `repair_codex_thread_state`

## Proposed Product Shape

### A. Codex Stream Stability Gate

New Doctor section:

`Codex Stream Stability`

Signals:
- Desktop transport: native WebSocket, BridgeDeck HTTP/SSE, unknown.
- Sentry stale stream count.
- Active app-server count.
- Pending/inflight turn count.
- Last stream terminal event status.
- Last proxy classification.
- Current selected provider circuit state.

Statuses:
- `ok`
- `websocket_transport_risky`
- `desktop_stream_state_stale`
- `proxy_port_mismatch`
- `provider_circuit_open`
- `capability_mismatch`
- `bridge_mode_recommended`

### B. Non-WebSocket Bridge Mode As A First-Class Route

Current Stability Route already writes:

```toml
model_provider = "bridgedeck"

[model_providers.bridgedeck]
name = "OpenAI"
base_url = "http://127.0.0.1:8876/accounts/<account_id>/v1"
wire_api = "responses"
experimental_bearer_token = "local-bridge"
requires_openai_auth = false
supports_websockets = false
```

Product change:
- Keep the user-facing name as "Stability Route".
- Make it a deliberate fallback for repeated native WebSocket failure.
- Keep restore-native available, but do not present restart as the main fix.

### C. Capability Compatibility Matrix

Store per provider/account:

```json
{
  "websocket": "disabled",
  "image_input": "probe",
  "image_generation": "disabled",
  "web_search": "probe",
  "tools": "enabled",
  "reasoning_effort": ["low", "medium", "high", "xhigh"],
  "reasoning_summary": "enabled"
}
```

Rules:
- `enabled`: advertise and pass through.
- `disabled`: do not advertise, strip from request where safe.
- `probe`: advertise only after successful live probe.
- `degraded`: auto-disabled after classified upstream failure.

### D. Provider Circuit Breaker

Circuit opens when any provider/account hits repeated:
- TLS EOF
- Cloudflare 403/challenge body
- `websocket closed before response.completed`
- no terminal stream event
- image/tool unsupported rejection
- proxy port mismatch

Circuit payload:

```json
{
  "provider_id": "...",
  "account_id": "...",
  "reason": "websocket_terminal_missing",
  "opened_at": "...",
  "open_until": "...",
  "evidence": ["last request id", "last status", "log hash"],
  "next_route": "bridgedeck_http_sse"
}
```

### E. Codex State Repair Readiness

Read-only first:
- Parse Codex Sentry scope.
- Parse `state_5.sqlite` thread/provider columns when available.
- Parse recent rollout session metadata.
- Compare against current config/provider catalog.

Repair later:
- Only touch known stale BridgeDeck/AiMaMi router/provider references.
- Backup DB and rollout file before any write.
- Keep a manifest for rollback.

## Implementation Sequence

### Milestone 1: Detection

Status: implemented.

Deliverables:
- Added Sentry app-state reader.
- Added freshness guard for Sentry evidence.
- Added `desktop_stream_state_stale` classification.
- Added Doctor output that routes fresh stale stream state to guarded Stability Route canary.
- Added tests with fixture Sentry payloads.

Acceptance:
- Given `thread_count_streaming_without_active_runtime > 0`, Doctor returns `desktop_stream_state_stale`.
- Fresh evidence returns `run_stability_route_canary`, not `hard_restart_codex`.
- Old evidence returns `desktop_app_state_unfresh`, not a route change.

### Milestone 2: Stability Route Canary

Deliverables:
- Promote Bridge mode wording to Stability Route.
- Expose guarded canary state with preconditions.
- Enable Stability Route only when app-state evidence is fresh.
- Validate active config and app-state after a real streaming task.

Acceptance:
- `supports_websockets = false` is present.
- `/v1/models` still returns models.
- Doctor reports native WebSocket bypassed.
- A real streaming task completes with a terminal event.
- Fresh app-state after the canary does not show increasing stale stream ownership.

### Milestone 3: Capability Matrix

Deliverables:
- Add provider capability store.
- Add model payload shaping from matrix.
- Add image/search/tool unsupported classifiers.

Acceptance:
- Provider with `image_generation=disabled` does not advertise image generation.
- A 403 image-generation failure marks capability degraded.
- Plain text retry succeeds without changing account.

### Milestone 4: Circuit Breaker

Deliverables:
- Add provider/account circuit state.
- Integrate with auto-switch selection.
- Show open circuits in UI and health endpoint.

Acceptance:
- Repeated TLS EOF opens circuit.
- Auto-switch skips open circuit provider.
- Circuit expiry returns provider to probe state.

### Milestone 5: Thread/Config Cleanup

Deliverables:
- Read-only stale thread/provider report.
- Managed-block integrity repair.
- DB/rollout rollback manifest design.

Acceptance:
- Orphan provider ids are reported with exact file/row evidence.
- Repair only touches known managed references.
- Rollback manifest can restore prior values.

## Non-Goals

- Do not patch Codex Desktop internals.
- Do not kill or restart Codex as the primary fix path.
- Do not silently change user-selected providers.
- Do not erase non-BridgeDeck config.
- Do not hide upstream account/proxy failures behind generic retry.

## Next Assignment

Run Milestone 2 canary next.

The product can now say:

> Codex Desktop is in fresh stale WebSocket stream state. BridgeDeck local bridge and proxy are healthy enough. Run a guarded Stability Route canary through HTTP/SSE, then verify terminal stream completion and fresh app-state.

The next useful step is executing that canary against a real streaming task and recording pass/fail evidence.
