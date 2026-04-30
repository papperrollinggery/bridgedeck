#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx


AUTH_STORE_PATH = Path.home() / ".cc-switch" / "codex_oauth_auth.json"
CC_SWITCH_DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_USER_AGENT = "codex-local-bridge"
UPSTREAM_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TOKEN_REFRESH_BUFFER_SECS = 60
ACCOUNT_ROUTE_RE = re.compile(r"^/accounts/([^/]+)(/.*)?$")
UPSTREAM_PROXY_ENV = "CODEX_BRIDGE_UPSTREAM_PROXY"


@dataclass
class AccountRecord:
    account_id: str
    refresh_token: str
    email: str | None = None
    authenticated_at: int | None = None


@dataclass
class CachedToken:
    token: str
    expires_at: float

    def is_expiring_soon(self) -> bool:
        return (self.expires_at - time.time()) < TOKEN_REFRESH_BUFFER_SECS


def mask_proxy_url(proxy_url: str | None) -> str:
    if not proxy_url:
        return "direct"
    match = re.match(r"^(https?://)(?:[^@/]+@)?([^/]+)$", proxy_url.strip())
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return proxy_url


def get_upstream_proxy_url() -> str | None:
    value = os.environ.get(UPSTREAM_PROXY_ENV, "").strip()
    if not value:
        return None
    parsed = httpx.URL(value)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(
            f"{UPSTREAM_PROXY_ENV} only supports http:// or https:// proxies, got: {parsed.scheme}"
        )
    return value


def build_upstream_http_client(timeout: float) -> httpx.Client:
    proxy_url = get_upstream_proxy_url()
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "trust_env": False,
        "follow_redirects": True,
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


def truncate_log_text(value: str | None, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    safe_value = value.replace("\n", " ").strip()
    if len(safe_value) > limit:
        return safe_value[:limit] + "..."
    return safe_value


def log_upstream_result(
    request_type: str,
    account_id: str | None,
    success: bool,
    *,
    status_code: int | None = None,
    detail: str | None = None,
) -> None:
    proxy_mode = mask_proxy_url(os.environ.get(UPSTREAM_PROXY_ENV))
    account_label = account_id or "default"
    summary = (
        f"[upstream] type={request_type} account_id={account_label} proxy={proxy_mode} "
        f"success={str(success).lower()}"
    )
    if status_code is not None:
        summary += f" status={status_code}"
    if detail:
        safe_detail = truncate_log_text(detail)
        summary += f" detail={safe_detail}"
    print(summary, file=sys.stderr)


def summarize_request_shape(body: dict[str, Any]) -> dict[str, Any]:
    shape: dict[str, Any] = {"keys": sorted(body.keys())}

    for key in ("stream", "store", "tool_choice", "parallel_tool_calls", "model"):
        if key in body:
            shape[key] = body.get(key)

    if "instructions" in body:
        instructions = body.get("instructions")
        shape["instructions_kind"] = type(instructions).__name__
        shape["has_instructions"] = bool(instructions)

    include = body.get("include")
    if isinstance(include, list):
        shape["include"] = sorted({item for item in include if isinstance(item, str)})

    tools = body.get("tools")
    if isinstance(tools, list):
        shape["tools_count"] = len(tools)

    input_items = body.get("input")
    if isinstance(input_items, list):
        item_types: set[str] = set()
        roles: set[str] = set()
        content_types: set[str] = set()
        for item in input_items:
            if isinstance(item, dict):
                item_type = item.get("type")
                if isinstance(item_type, str):
                    item_types.add(item_type)
                role = item.get("role")
                if isinstance(role, str):
                    roles.add(role)
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            part_type = part.get("type")
                            if isinstance(part_type, str):
                                content_types.add(part_type)
            else:
                item_types.add(type(item).__name__)
        shape["input_count"] = len(input_items)
        if item_types:
            shape["input_item_types"] = sorted(item_types)
        if roles:
            shape["input_roles"] = sorted(roles)
        if content_types:
            shape["input_content_types"] = sorted(content_types)
    elif "input" in body:
        shape["input_kind"] = type(input_items).__name__

    removed_fields = [key for key in ("max_output_tokens", "temperature", "top_p") if key in body]
    if removed_fields:
        shape["legacy_fields_present"] = sorted(removed_fields)

    return shape


def extract_reasoning_effort(payload: dict[str, Any]) -> str | None:
    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    effort = reasoning.get("effort")
    return effort if isinstance(effort, str) and effort else None


def lookup_bridge_provider_names(account_id: str | None) -> list[str]:
    if not account_id or not CC_SWITCH_DB_PATH.exists():
        return []

    query = """
        SELECT name
        FROM providers
        WHERE json_extract(meta, '$.authBinding.accountId') = ?
          AND json_extract(settings_config, '$.env.ANTHROPIC_AUTH_TOKEN') = 'local-bridge'
        ORDER BY name
    """
    try:
        with sqlite3.connect(CC_SWITCH_DB_PATH) as conn:
            rows = conn.execute(query, (account_id,)).fetchall()
    except sqlite3.Error:
        return []

    return [name for (name,) in rows if isinstance(name, str)]


def log_upstream_diagnostic(
    request_type: str,
    account_id: str | None,
    *,
    status_code: int,
    route_path: str,
    response_headers: httpx.Headers | None = None,
    request_shape: dict[str, Any] | None = None,
    normalized_shape: dict[str, Any] | None = None,
    error_detail: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": request_type,
        "account_id": account_id or "default",
        "route_path": route_path,
        "status": status_code,
    }
    provider_names = lookup_bridge_provider_names(account_id)
    if provider_names:
        payload["provider_names"] = provider_names
    if response_headers is not None:
        upstream_request_id = response_headers.get("x-request-id")
        if upstream_request_id:
            payload["x_request_id"] = upstream_request_id
        processing_ms = response_headers.get("openai-processing-ms")
        if processing_ms:
            payload["openai_processing_ms"] = processing_ms
        response_content_type = response_headers.get("content-type")
        if response_content_type:
            payload["content_type"] = response_content_type
    if request_shape:
        payload["request_shape"] = request_shape
    if normalized_shape:
        payload["normalized_shape"] = normalized_shape
    safe_error_detail = truncate_log_text(error_detail, limit=800)
    if safe_error_detail:
        payload["error_detail"] = safe_error_detail
    print(
        f"[upstream-diagnostic] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
        file=sys.stderr,
    )


class AuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._token_cache: dict[str, CachedToken] = {}

    def load(self) -> tuple[dict[str, AccountRecord], str | None]:
        raw = json.loads(self.path.read_text())
        accounts = {
            account_id: AccountRecord(
                account_id=account_id,
                refresh_token=data["refresh_token"],
                email=data.get("email"),
                authenticated_at=data.get("authenticated_at"),
            )
            for account_id, data in raw.get("accounts", {}).items()
        }
        return accounts, raw.get("default_account_id")

    def save(self, accounts: dict[str, AccountRecord], default_account_id: str | None) -> None:
        payload = {
            "version": 1,
            "accounts": {
                account_id: {
                    "account_id": record.account_id,
                    "email": record.email,
                    "refresh_token": record.refresh_token,
                    "authenticated_at": record.authenticated_at,
                }
                for account_id, record in accounts.items()
            },
            "default_account_id": default_account_id,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def get_access_token(self, requested_account_id: str | None) -> tuple[str, str]:
        with self._lock:
            accounts, default_account_id = self.load()
            account_id = requested_account_id or default_account_id
            if not account_id or account_id not in accounts:
                raise RuntimeError(f"account not found: {requested_account_id or 'default'}")

            cached = self._token_cache.get(account_id)
            if cached and not cached.is_expiring_soon():
                return account_id, cached.token

            record = accounts[account_id]
            token_data = self._refresh_token(record.refresh_token)

            new_refresh = token_data.get("refresh_token")
            if new_refresh and new_refresh != record.refresh_token:
                record.refresh_token = new_refresh
                accounts[account_id] = record
                self.save(accounts, default_account_id)

            access_token = token_data["access_token"]
            expires_in = int(token_data.get("expires_in", 3600))
            self._token_cache[account_id] = CachedToken(
                token=access_token,
                expires_at=time.time() + expires_in,
            )
            return account_id, access_token

    def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        try:
            with build_upstream_http_client(timeout=30.0) as client:
                response = client.post(
                    OAUTH_TOKEN_URL,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": CODEX_USER_AGENT,
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": CODEX_CLIENT_ID,
                        "scope": "openid profile email",
                    },
                )
            response.raise_for_status()
            log_upstream_result("oauth_token", None, True, status_code=response.status_code)
            return response.json()
        except httpx.HTTPStatusError as exc:
            log_upstream_result(
                "oauth_token",
                None,
                False,
                status_code=exc.response.status_code,
                detail=exc.response.text,
            )
            raise
        except Exception as exc:
            log_upstream_result("oauth_token", None, False, detail=f"{type(exc).__name__}: {exc}")
            raise


def normalize_request_body(body: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(body)
    normalized["store"] = False
    # ChatGPT's Codex backend rejects non-streaming responses on this endpoint.
    # The bridge is dedicated to CC Switch/Claude flows, which already expect SSE.
    normalized["stream"] = True
    normalized["tool_choice"] = normalized.get("tool_choice", "auto")
    normalized["parallel_tool_calls"] = normalized.get("parallel_tool_calls", False)
    normalized["instructions"] = normalized.get("instructions", "")
    normalized["tools"] = normalized.get("tools", [])

    model = normalized.get("model")
    if isinstance(model, str):
        normalized_model, default_effort = normalize_codex_model_and_effort(model)
        if normalized_model != model:
            print(
                f"[bridge-normalize] model {model} -> {normalized_model}",
                file=sys.stderr,
            )
            normalized["model"] = normalized_model
        if default_effort and not has_reasoning_effort(normalized):
            normalized["reasoning"] = {"effort": default_effort}
            print(
                f"[bridge-normalize] reasoning.effort -> {default_effort} (model={normalized['model']})",
                file=sys.stderr,
            )

    include = normalized.get("include")
    includes = [item for item in include if isinstance(item, str)] if isinstance(include, list) else []
    includes = [item for item in includes if item != "reasoning.summary"]
    if "reasoning.encrypted_content" not in includes:
        includes.append("reasoning.encrypted_content")
    normalized["include"] = includes

    for key in ("max_output_tokens", "temperature", "top_p"):
        normalized.pop(key, None)

    input_items = normalized.get("input")
    if isinstance(input_items, list):
        rewritten = []
        for item in input_items:
            if isinstance(item, dict) and "role" in item and "type" not in item:
                cloned = dict(item)
                cloned["type"] = "message"
                rewritten.append(cloned)
            else:
                rewritten.append(item)
        normalized["input"] = rewritten

    return normalized


def parse_sse_blocks(raw_bytes: bytes) -> list[tuple[str | None, dict[str, Any] | None]]:
    blocks: list[tuple[str | None, dict[str, Any] | None]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    text = raw_bytes.decode("utf-8", "replace")

    for line in text.splitlines():
        if line == "":
            if data_lines:
                payload_text = "\n".join(data_lines).strip()
                payload: dict[str, Any] | None = None
                if payload_text and payload_text != "[DONE]":
                    try:
                        decoded = json.loads(payload_text)
                        if isinstance(decoded, dict):
                            payload = decoded
                    except Exception:  # noqa: BLE001
                        payload = None
                blocks.append((event_name, payload))
            event_name = None
            data_lines = []
            continue

        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())

    if data_lines:
        payload_text = "\n".join(data_lines).strip()
        payload: dict[str, Any] | None = None
        if payload_text and payload_text != "[DONE]":
            try:
                decoded = json.loads(payload_text)
                if isinstance(decoded, dict):
                    payload = decoded
            except Exception:  # noqa: BLE001
                payload = None
        blocks.append((event_name, payload))

    return blocks


def build_non_stream_json_from_sse(raw_bytes: bytes, fallback_model: str | None = None) -> bytes:
    blocks = parse_sse_blocks(raw_bytes)
    completed_response: dict[str, Any] | None = None
    message_text_parts: list[str] = []
    final_text: str | None = None

    for event_name, payload in blocks:
        if not isinstance(payload, dict):
            continue
        if event_name == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                message_text_parts.append(delta)
        elif event_name == "response.output_text.done":
            text = payload.get("text")
            if isinstance(text, str):
                final_text = text
        elif event_name == "response.completed":
            response_obj = payload.get("response")
            if isinstance(response_obj, dict):
                completed_response = response_obj

    text = final_text if isinstance(final_text, str) else "".join(message_text_parts)

    if completed_response is None:
        completed_response = {
            "id": "resp_bridge_non_stream",
            "object": "response",
            "status": "completed",
            "model": fallback_model or "gpt-5.3-codex",
            "usage": None,
        }
    else:
        completed_response = dict(completed_response)

    output = completed_response.get("output")
    if not isinstance(output, list) or len(output) == 0:
        completed_response["output"] = [
            {
                "id": "msg_bridge_non_stream",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]

    return json.dumps(completed_response, ensure_ascii=False).encode("utf-8")


def has_reasoning_effort(body: dict[str, Any]) -> bool:
    reasoning = body.get("reasoning")
    return isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), str)


def supports_reasoning_effort_model(model: str) -> bool:
    model_lower = model.lower()
    if re.match(r"^o\d", model_lower):
        return True
    if not model_lower.startswith("gpt-"):
        return False
    rest = model_lower[4:]
    return bool(rest) and rest[0].isdigit() and rest[0] >= "5"


def normalize_codex_model_and_effort(model: str) -> tuple[str, str | None]:
    model_lower = model.strip().lower()
    if model_lower == "gpt-5.1-codex-max":
        return "gpt-5.4", "xhigh"
    if model_lower.endswith("-thinking"):
        base = model_lower[: -len("-thinking")]
        if supports_reasoning_effort_model(base):
            return base, "xhigh"
    return model, None


class CodexBridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexBridge/0.1"
    protocol_version = "HTTP/1.1"

    def _resolve_account_route(self) -> tuple[str | None, str]:
        match = ACCOUNT_ROUTE_RE.match(self.path)
        if not match:
            return None, self.path
        account_id = match.group(1)
        suffix = match.group(2) or "/"
        return account_id, suffix

    def do_GET(self) -> None:
        route_account_id, route_path = self._resolve_account_route()
        if route_path == "/health":
            payload = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self._write_bytes(payload)
            return
        if route_path == "/quota":
            try:
                requested_account_id = route_account_id or self.headers.get("x-account-id")
                account_id, access_token = self.server.auth_store.get_access_token(requested_account_id)
                upstream_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "ChatGPT-Account-Id": account_id,
                    "Accept": "application/json",
                    "User-Agent": CODEX_USER_AGENT,
                }
                with build_upstream_http_client(timeout=30.0) as client:
                    response = client.get(
                        f"{UPSTREAM_BASE_URL}/usage",
                        headers=upstream_headers,
                    )
                payload = response.content
                log_upstream_result("quota", account_id, response.is_success, status_code=response.status_code)
                if not response.is_success:
                    log_upstream_diagnostic(
                        "quota",
                        account_id,
                        status_code=response.status_code,
                        route_path=route_path,
                        response_headers=response.headers,
                        error_detail=payload.decode("utf-8", "replace"),
                    )
                self.send_response(response.status_code)
                self.send_header(
                    "Content-Type",
                    response.headers.get("content-type", "application/json"),
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self._write_bytes(payload)
            except httpx.HTTPStatusError as exc:
                log_upstream_result(
                    "quota",
                    route_account_id,
                    False,
                    status_code=exc.response.status_code,
                    detail=exc.response.text,
                )
                self._write_json_error(exc.response.status_code, exc.response.text)
            except Exception as exc:  # noqa: BLE001
                log_upstream_result(
                    "quota", route_account_id, False, detail=f"{type(exc).__name__}: {exc}"
                )
                self._write_json_error(500, f"{type(exc).__name__}: {exc}")
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        route_account_id, route_path = self._resolve_account_route()
        if route_path != "/v1/responses":
            self.send_error(404, "Not Found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            request_body = json.loads(raw_body.decode("utf-8"))
            requested_stream = bool(request_body.get("stream", False))

            requested_account_id = route_account_id or self.headers.get("chatgpt-account-id")
            account_id, access_token = self.server.auth_store.get_access_token(requested_account_id)
            normalized_body = normalize_request_body(request_body)
            is_stream = requested_stream

            upstream_headers = {
                "Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-Id": account_id,
                "Content-Type": "application/json",
                "Accept": self.headers.get("Accept", "application/json"),
                "User-Agent": CODEX_USER_AGENT,
                "Originator": "cc-switch-local-bridge",
            }

            if self.headers.get("anthropic-beta"):
                upstream_headers["anthropic-beta"] = self.headers["anthropic-beta"]

            upstream_url = f"{UPSTREAM_BASE_URL}/responses"

            with build_upstream_http_client(timeout=600.0) as client, client.stream(
                "POST",
                upstream_url,
                headers=upstream_headers,
                json=normalized_body,
            ) as response:
                error_body = None
                if not response.is_success:
                    error_body = response.read()
                self.send_response(response.status_code)
                log_upstream_result(
                    "responses",
                    account_id,
                    response.is_success,
                    status_code=response.status_code,
                    detail=None
                    if response.is_success
                    else error_body.decode("utf-8", "replace") if error_body is not None else None,
                )
                if not response.is_success:
                    log_upstream_diagnostic(
                        "responses",
                        account_id,
                        status_code=response.status_code,
                        route_path=route_path,
                        response_headers=response.headers,
                        request_shape=summarize_request_shape(request_body),
                        normalized_shape=summarize_request_shape(normalized_body),
                        error_detail=error_body.decode("utf-8", "replace") if error_body is not None else None,
                    )

                passthrough_headers = [
                    "content-type",
                    "cache-control",
                    "x-request-id",
                    "openai-processing-ms",
                ]
                for key in passthrough_headers:
                    value = response.headers.get(key)
                    if value:
                        if key == "content-type" and not is_stream:
                            continue
                        self.send_header(key, value)
                if not is_stream:
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()

                if is_stream:
                    requested_effort = extract_reasoning_effort(normalized_body)
                    requested_model = (
                        normalized_body.get("model")
                        if isinstance(normalized_body.get("model"), str)
                        else None
                    )
                    print(
                        f"[bridge-model] account_id={account_id} model={requested_model or 'unknown'} effort={requested_effort or 'unknown'}",
                        file=sys.stderr,
                    )
                    if error_body is not None:
                        self._write_bytes(error_body, flush=True)
                        return
                    for chunk in response.iter_bytes():
                        if chunk:
                            self._write_bytes(chunk, flush=True)
                else:
                    body = error_body if error_body is not None else response.read()
                    if response.is_success:
                        body = build_non_stream_json_from_sse(
                            body,
                            normalized_body.get("model")
                            if isinstance(normalized_body.get("model"), str)
                            else None,
                        )
                    self._write_bytes(body, flush=True)
        except httpx.HTTPStatusError as exc:
            self._write_json_error(exc.response.status_code, exc.response.text)
        except Exception as exc:  # noqa: BLE001
            self._write_json_error(500, f"{type(exc).__name__}: {exc}")

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[codex-bridge] {self.address_string()} - {fmt % args}\n")

    def _write_json_error(self, status: int, message: str) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self._write_bytes(payload)

    def _write_bytes(self, payload: bytes, *, flush: bool = False) -> None:
        try:
            self.wfile.write(payload)
            if flush:
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


class CodexBridgeServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], auth_store: AuthStore) -> None:
        super().__init__(server_address, handler)
        self.auth_store = auth_store


def main() -> int:
    host = os.environ.get("CODEX_BRIDGE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("CODEX_BRIDGE_PORT", str(DEFAULT_PORT)))
    auth_store_path = Path(os.environ.get("CODEX_AUTH_STORE_PATH", str(AUTH_STORE_PATH)))

    if not auth_store_path.exists():
        print(f"auth store not found: {auth_store_path}", file=sys.stderr)
        return 1

    try:
        proxy_url = get_upstream_proxy_url()
    except Exception as exc:  # noqa: BLE001
        print(f"invalid upstream proxy config: {exc}", file=sys.stderr)
        return 1

    auth_store = AuthStore(auth_store_path)
    server = CodexBridgeServer((host, port), CodexBridgeHandler, auth_store)
    print(
        f"codex bridge listening on http://{host}:{port} (upstream_proxy={mask_proxy_url(proxy_url)})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
