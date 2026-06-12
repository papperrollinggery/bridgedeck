# Security Policy / 安全政策

## Local-Only Design / 本地优先设计

BridgeDeck is designed for local use. It reads and writes files that may contain account identifiers and OAuth tokens.

BridgeDeck 设计为本地使用。它会读写可能包含账号标识和 OAuth token 的文件。

Default bind address:

默认监听地址：

```text
127.0.0.1:8899
```

Non-loopback binding requires `--allow-remote`. Remote mode is read-only by default and cannot reveal full tokens. Write APIs and token reveal require `--allow-remote-write`.

非本机监听必须传入 `--allow-remote`。远程模式默认只读，不能显示完整 token。写入 API 和 token 显示需要额外传入 `--allow-remote-write`。

## Sensitive Data / 敏感数据

The tool may access:

本工具可能访问：

- `~/.cc-switch/codex_oauth_auth.json`
- `~/.cc-switch/bridgedeck-auth.json`
- `~/.cc-switch/cc-switch.db`
- `~/.cc-switch/bridgedeck-local-bridge-state.json`
- `~/.codex/auth.json`
- `~/.codex/accounts/snapshots/*.json`
- `~/.codex-cli-*/auth.json`

Do not publish these files.

不要公开这些文件。

## Browser/API Protections / 浏览器与 API 防护

- API requests require a per-run browser token.
- API 请求需要本次启动生成的浏览器令牌。
- Full tokens are not returned by default.
- 默认不返回完整 token。
- `include_secrets=1` requires the browser token.
- `include_secrets=1` 必须携带浏览器令牌。
- Host/Origin checks reject unexpected browser contexts.
- Host/Origin 校验会拒绝异常浏览器上下文。
- Cross-site Fetch Metadata is rejected where browsers provide it.
- 浏览器提供 Fetch Metadata 时会拒绝跨站请求。
- Remote read-only mode redacts account identifiers, emails, local paths, and bridge account URLs in API responses.
- 远程只读模式会在 API 响应中脱敏账号标识、邮箱、本地路径和 bridge 账号 URL。
- HTML responses use a nonce-based CSP and frame blocking headers.
- HTML 响应使用 nonce CSP 和防嵌入响应头。
- Request bodies are size-limited.
- 请求体有大小限制。

## Reporting a Vulnerability / 报告漏洞

Prefer GitHub Security Advisories if the repository enables them. Otherwise open an issue with all sensitive details removed.

如果仓库启用了 GitHub Security Advisories，优先使用它报告。否则请创建 issue，并先删除所有敏感信息。

Remove before posting:

发布前删除：

- OAuth access tokens
- OAuth refresh tokens
- account IDs if you consider them private
- emails
- private local paths
- screenshots containing account data
- local token snapshots or generated diagnostics
- 包含账号信息的截图
- 本机 token 快照或生成的诊断文件

Expected handling:

预期处理：

- Critical token exposure: best effort response within 48 hours.
- 严重 token 泄露：尽力在 48 小时内响应。
- Other security bugs: best effort response within 7 days.
- 其他安全问题：尽力在 7 天内响应。

## Supported Scope / 支持范围

This is a local helper for CC Switch configuration. It does not provide account authorization, token issuance, hosted proxy service, or cloud sync.

本项目只是 CC Switch 配置的本地辅助工具，不提供账号授权、token 签发、托管代理服务或云同步。
