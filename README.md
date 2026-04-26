# BridgeDeck / BridgeDeck 本地账号桥接面板

Local web helper for managing CC Switch Codex OAuth bridge providers and launcher-only Codex CLI account routes.

本工具是一个本地网页助手，用于管理 CC Switch 的 Codex OAuth 桥接 Provider，以及为 Codex CLI 生成不复制 token 的账号启动器。

## What It Does / 功能

- Create or repair Claude providers that route through a local Codex bridge.
- 创建或修复走本地 Codex bridge 的 Claude Provider。
- Keep Claude provider account binding and quota identity intact.
- 保留 Claude Provider 的账号绑定和额度身份。
- Generate launcher-only Codex CLI routes under `~/.cc-switch/codex-cli-launchers/`.
- 在 `~/.cc-switch/codex-cli-launchers/` 下生成 launcher-only Codex CLI 账号路由。
- Detect stale tokenful `~/.codex-cli-*` profiles without copying or refreshing OpenAI tokens.
- 检测旧的 tokenful `~/.codex-cli-*` 配置，不复制、不刷新 OpenAI token。
- Detect Codex Desktop config state, and optionally set a default Codex account for tools that cannot pass CLI flags.
- 检测 Codex Desktop 配置状态，并可选设置默认 Codex 账号，供无法输入 CLI 参数的工具使用。
- Detect Codex provider account/token mismatch.
- 检查 Codex Provider 的显示账号和实际 token 账号是否不一致。
- Hide tokens by default; reveal only on explicit user action.
- 默认隐藏 token，只有用户主动点击才显示。
- Back up local files before writes.
- 写入前自动备份本地文件。

## Disclaimer / 免责声明

This project is an independent local helper. It is not affiliated with CC Switch, OpenAI, Anthropic, GitHub, or Microsoft.

本项目是独立本地辅助工具，与 CC Switch、OpenAI、Anthropic、GitHub、Microsoft 无官方关联。

Using reverse-proxy, bridge, OAuth, or account-routing workflows may be subject to the terms of the relevant services. You are responsible for deciding whether a workflow is allowed for your account and environment.

使用反向代理、桥接、OAuth 或账号路由相关流程，可能受到对应服务条款约束。是否适合你的账号和环境，由使用者自行判断。

## Requirements / 运行要求

- macOS
- Python 3.10+
- CC Switch installed and configured
- 已安装并配置 CC Switch
- Codex OAuth accounts already logged in inside CC Switch
- 已在 CC Switch 内完成 Codex OAuth 账号登录
- Optional: local Codex bridge running on `127.0.0.1:8876`
- 可选：本地 Codex bridge 已运行在 `127.0.0.1:8876`

Tested locally on macOS with the system Python 3 runtime. CC Switch schema compatibility is checked at runtime through SQLite columns where possible.

本工具在 macOS 系统 Python 3 环境下测试。CC Switch 数据库兼容性会尽量通过 SQLite 字段检测处理。

## Quick Start / 快速启动

```bash
chmod +x run-bridgedeck.command
./run-bridgedeck.command
```

Open / 打开：

```text
http://127.0.0.1:8899
```

Manual start / 手动启动：

```bash
python3 bridgedeck.py --host 127.0.0.1 --port 8899
```

## Install From DMG / 通过 DMG 安装

1. Download `BridgeDeck.dmg` from GitHub Releases.
2. Open the DMG and drag the app to `Applications`, or run it directly.
3. If macOS Gatekeeper blocks the unsigned app, right-click the app and choose `Open`.

1. 从 GitHub Releases 下载 `BridgeDeck.dmg`。
2. 打开 DMG，将 App 拖到 `Applications`，或直接运行。
3. 如果 macOS Gatekeeper 拦截未签名 App，右键 App 选择“打开”。

## Main Workflows / 主要使用流程

### Claude via a ChatGPT Account / Claude 使用某个 ChatGPT 账号

1. Log in to the target Codex OAuth account in CC Switch.
2. Open this tool.
3. In `Claude 桥接账号`, select the account.
4. Keep `设为当前` enabled if you want Claude Code to switch immediately.
5. Click `创建/更新 Claude 桥接`.
6. In `Claude Provider 管理`, confirm the provider shows `settings=true`.

1. 先在 CC Switch 里登录目标 Codex OAuth 账号。
2. 打开本工具。
3. 在 `Claude 桥接账号` 中选择账号。
4. 如果要立刻切换 Claude Code，保持 `设为当前` 勾选。
5. 点击 `创建/更新 Claude 桥接`。
6. 在 `Claude Provider 管理` 中确认目标 Provider 显示 `settings=true`。

### Standalone Codex CLI / 单独 Codex CLI

This creates a per-account launcher and does not change the global default Codex account.

单独 Codex CLI 只生成某个账号的独立启动器，不改变全局默认 Codex 账号。

1. In `单独 Codex CLI`, click `选用` for the account.
2. Keep the generated directory such as `~/.codex-cli-pro`.
3. Click `生成启动器`.
4. Start CLI using the displayed command:

1. 在 `单独 Codex CLI` 中，对目标账号点击 `选用`。
2. 保持生成的目录，例如 `~/.codex-cli-pro`。
3. 点击 `生成启动器`。
4. 使用页面输出命令启动 CLI：

```bash
CODEX_HOME=/Users/you/.codex-cli-pro OPENAI_API_KEY=local-bridge codex -c 'base_url="http://127.0.0.1:8876/accounts/<account_id>/v1"'
```

or use the generated launcher:

也可以使用自动生成的启动器：

```text
~/.cc-switch/codex-cli-launchers/codex-<name>.command
```

### Global Codex CLI / 全局 Codex CLI

For tools such as Paperclip that call the default `codex` command and do not let you enter a launch command, use `设为全局 Codex CLI`.

对于 Paperclip 这类直接调用默认 `codex`、不提供命令输入位置的工具，使用 `设为全局 Codex CLI`。

This writes only `base_url` in `~/.codex/config.toml` after making a backup. It does not copy `access_token`, `refresh_token`, or `id_token`.

该操作会先备份，再只写入 `~/.codex/config.toml` 里的 `base_url`。不会复制 `access_token`、`refresh_token` 或 `id_token`。

## Files Read or Written / 读写文件

The tool reads/writes these local files:

本工具会读写以下本地文件：

- `~/.cc-switch/cc-switch.db`
- `~/.cc-switch/settings.json`
- `~/.cc-switch/codex_oauth_auth.json`
- `~/.codex-cli-*`
- `~/.cc-switch/codex-cli-launchers/*`
- `~/.codex/config.toml` only when `默认都用这个账号` is clicked
- 只有点击 `默认都用这个账号` 时才会写入 `~/.codex/config.toml`

Codex CLI launchers no longer write `auth.json` or copy OAuth tokens. Migration may disable an old `~/.codex-cli-*/auth.json` after backing it up.

Codex CLI 启动器不再写 `auth.json`，也不复制 OAuth token。迁移旧配置时会先备份，再禁用旧的 `~/.codex-cli-*/auth.json`。

By default, it reads but does not overwrite the default Codex config:

默认只读取、不覆盖默认 Codex 配置：

- `~/.codex/config.toml`
- `~/.codex/.env`

Backups are written to:

备份文件写入：

```text
~/.cc-switch/bridgedeck-backups/
```

## Security Model / 安全模型

- The app binds to `127.0.0.1` by default.
- 默认只监听 `127.0.0.1`。
- Non-loopback binding requires `--allow-remote`.
- 非本机监听必须显式传入 `--allow-remote`。
- Remote mode is read-only by default and cannot reveal full tokens.
- 远程模式默认只读，不能显示完整 token。
- Remote read-only mode redacts account IDs, email addresses, local paths, and bridge account URLs in API responses.
- 远程只读模式会在 API 响应中脱敏 account id、邮箱、本地路径和 bridge 账号 URL。
- Write APIs and token reveal in remote mode require `--allow-remote-write`.
- 远程模式下写入和显示 token 必须额外传入 `--allow-remote-write`。
- All API requests require a per-run browser token.
- 所有 API 请求都需要本次启动生成的浏览器令牌。
- API requests reject cross-site Fetch Metadata where supported by the browser.
- 浏览器支持 Fetch Metadata 时，API 会拒绝跨站请求。
- Full tokens are not returned by `/api/data` unless the UI explicitly requests `include_secrets=1`.
- `/api/data` 默认不返回完整 token，只有 UI 明确请求 `include_secrets=1` 才返回。
- The page sends CSP, frame blocking, no-store, nosniff, and referrer policy headers.
- 页面会发送 CSP、防嵌入、no-store、nosniff 和 referrer policy 安全响应头。
- Do not expose this app to a public network.
- 不要把本工具暴露到公网。

## Privacy / 隐私

The UI may show account IDs, email addresses, local paths, and masked tokens. Do not include screenshots or logs from your real environment in public issues unless you redact them first.

页面可能显示 account id、邮箱、本地路径和脱敏 token。提交公开 issue 前，请先对截图和日志做脱敏。

Never publish:

不要公开：

- OAuth access tokens
- OAuth refresh tokens
- `auth.json`
- `codex_oauth_auth.json`
- `cc-switch.db`
- private screenshots with account IDs or emails
- 带账号 ID、邮箱、本地路径的未脱敏截图

## Uninstall / 卸载

Remove the app or this folder. The tool does not install background services.

删除 App 或本目录即可。本工具不会安装后台服务。

Optional generated files:

可选清理自动生成文件：

```bash
rm -rf ~/.cc-switch/codex-cli-launchers
rm -rf ~/.cc-switch/bridgedeck-backups
rm -rf ~/.codex-cli-*
```

## Package macOS DMG / 打包 macOS DMG

```bash
chmod +x package-bridgedeck-dmg.command
./package-bridgedeck-dmg.command
```

Output / 输出：

```text
dist/BridgeDeck.dmg
```

For public releases, add a checksum:

公开发布建议同时提供校验值：

```bash
shasum -a 256 dist/BridgeDeck.dmg
```

## Development Checks / 开发检查

```bash
python3 -m py_compile bridgedeck.py
python3 -m unittest discover -s tests
python3 bridgedeck.py --host 127.0.0.1 --port 8899
zsh -n run-bridgedeck.command
zsh -n package-bridgedeck-dmg.command
```

## CLI Options / 命令行参数

```text
--db PATH              path to cc-switch.db
--settings PATH        path to settings.json
--auth-store PATH      path to codex_oauth_auth.json
--host HOST            listen host, default 127.0.0.1
--port PORT            listen port, default 8899
--allow-remote         allow non-loopback bind; read-only and no secret reveal
--allow-remote-write   allow write APIs and token reveal in remote mode
```

```text
--db PATH              cc-switch.db 路径
--settings PATH        settings.json 路径
--auth-store PATH      codex_oauth_auth.json 路径
--host HOST            监听地址，默认 127.0.0.1
--port PORT            监听端口，默认 8899
--allow-remote         允许非本机监听；默认只读且不能显示完整 token
--allow-remote-write   允许远程模式写入和显示完整 token
```

## Project Layout / 项目结构

```text
bridgedeck.py                   local web app and API / 本地网页应用和 API
run-bridgedeck.command          macOS launcher / macOS 启动脚本
package-bridgedeck-dmg.command  macOS app/dmg packager / macOS 打包脚本
README.md                      documentation / 文档
SECURITY.md                    security policy / 安全说明
CONTRIBUTING.md                contribution guide / 贡献说明
CHANGELOG.md                   changelog / 变更记录
OPEN_SOURCE_CHECKLIST.md       release checklist / 开源发布清单
LICENSE                        MIT license / MIT 许可证
.github/                       issue and PR templates / issue 和 PR 模板
```

## Release Checklist / 发布检查

```bash
python3 -m py_compile bridgedeck.py
python3 -m unittest discover -s tests
zsh -n run-bridgedeck.command
zsh -n package-bridgedeck-dmg.command
./package-bridgedeck-dmg.command
shasum -a 256 dist/BridgeDeck.dmg
```

Before publishing, make sure the repository does not contain:

发布前确认仓库不包含：

- `private-notes/`
- `__pycache__/`
- `.env`
- `*.db`
- `auth.json`
- `codex_oauth_auth.json`
- screenshots with private account data
- 含私人账号信息的截图

## License / 许可证

MIT
