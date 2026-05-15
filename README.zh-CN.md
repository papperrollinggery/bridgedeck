# BridgeDeck

CC Switch、Codex OAuth 账号、Claude Code、Codex CLI、本地 OpenAI/Anthropic 兼容 API 的本机账号控制台。

语言：[English](README.md) | [简体中文](README.zh-CN.md)

BridgeDeck 是本地 macOS 辅助工具。它不提供云端代理，不签发 token，也不会把 OAuth token 复制到生成的 Codex CLI 配置里。它读取本机 CC Switch 和 Codex 配置，然后提供更安全的账号路由、桥接 Provider 修复、本地 API 配置、用量查看和诊断界面。

BridgeDeck 是独立项目，与 CC Switch、OpenAI、Anthropic、GitHub、Microsoft 或任何桌面客户端厂商都没有官方关联。桥接、OAuth、gateway 和账号路由流程可能受你所使用服务的条款约束。

## 解决什么问题

当一台机器里有多个 ChatGPT/Codex OAuth 账号，并且不同工具需要不同入口时，BridgeDeck 负责把这些关系理清：

- Claude Code 需要一个 Claude 兼容 Provider，但实际路由到指定 Codex 账号。
- Codex CLI 需要独立账号启动器，或者需要设置全局默认账号。
- 第三方工具需要 OpenAI 兼容的 `base_url` 和本地占位 key。
- Claude Desktop 或 Anthropic 兼容客户端需要本地 `/v1/messages` 桥接。
- 账号额度、Provider 绑定、真实 token 身份需要核对，但不应该暴露真实 token。

## 主要能力

- **BridgeDeck 内置 ChatGPT 授权**：在 BridgeDeck 内生成 OpenAI 设备验证码，在浏览器完成授权，然后把账号加入或更新到 CC Switch Local Bridge Provider。
- **Claude Code 桥接 Provider**：创建、修复、检查走 `127.0.0.1:8876` 的 Claude Provider。
- **Codex CLI 路由**：生成只负责启动的单账号 Codex CLI launcher，也可以设置全局 Codex CLI 默认账号。
- **OpenAI 兼容本地 API**：提供账号级 `/v1/responses`、`/v1/chat/completions`、`/v1/models`。
- **Anthropic 兼容本地 API**：提供 `/v1/messages`，供 Claude 风格客户端使用。
- **用量仪表盘**：显示请求数、Token、缓存写入、缓存命中、缓存未命中、命中率、状态、入口来源、请求模型和实际路由模型。
- **账号状态检查**：对比 CC Switch Provider 绑定、真实 OAuth 身份、Claude 配置、Codex CLI 配置、Desktop/全局 Codex 状态。
- **隐私优先 UI**：默认遮罩账号 ID、邮箱、本地路径和 token；写入操作需要明确本地点击。

## 运行端口

| 端口 | 组件 | 用途 |
| --- | --- | --- |
| `8899` | BridgeDeck UI | 本地网页控制台 |
| `8876` | Local Codex Bridge | 账号级 OpenAI/Anthropic 兼容 API |
| `15721` | CC Switch | 已安装的 CC Switch 服务 |

BridgeDeck 默认只监听 `127.0.0.1`。

## 安装

### 下载 macOS App

1. 从 [GitHub Releases](https://github.com/papperrollinggery/bridgedeck/releases) 下载 `BridgeDeck.dmg`。
2. 打开 DMG，把 `BridgeDeck.app` 拖到 `Applications`，也可以直接运行。
3. 如果 macOS 拦截未签名 App，右键 App，选择“打开”。

点击 App 图标后，BridgeDeck 会显示原生选择框：

- `打开 UI`：启动或打开 `8899` 控制台。
- `只启动 Bridge`：只启动 `8876` Local Codex Bridge。
- `关闭 UI 保留 Bridge`：关闭 `8899` UI，但保留 `8876` 继续运行。

### 从源码运行

```bash
chmod +x run-bridgedeck.command
./run-bridgedeck.command
```

手动启动 UI：

```bash
python3 bridgedeck.py --host 127.0.0.1 --port 8899
```

手动打开 UI：

```text
http://127.0.0.1:8899
```

只操作 Local Codex Bridge：

```bash
python3 bridgedeck.py --local-bridge start
python3 bridgedeck.py --local-bridge status
python3 bridgedeck.py --local-bridge restart
python3 bridgedeck.py --local-bridge stop
```

## 常用流程

### 授权或刷新 ChatGPT/Codex 账号

1. 打开 BridgeDeck。
2. 进入 `入口切换`。
3. 点击 `生成授权验证码`。
4. 打开页面显示的 OpenAI 设备授权页。
5. 输入验证码并确认授权。
6. 回到 BridgeDeck，等待状态完成。
7. 新账号点击 `加入 CC Switch`，已有账号点击 `更新 CC Switch`。

BridgeDeck 只把 refresh token 写入 CC Switch 兼容的 OAuth 账号池，不会把 access token 返回给页面。

### 让 Claude Code 使用指定 ChatGPT 账号

1. 确认目标账号已在 CC Switch 里存在，或先通过 BridgeDeck 授权。
2. 打开 `入口切换`。
3. 在 `Claude Code` 区域选择账号。
4. 应用到 Claude Code。
5. 在状态矩阵里确认当前账号正确，并且没有 Provider 账号不一致。

### 创建单独 Codex CLI 启动器

当某个终端或自动化任务只应该使用指定账号，但不想改全局默认账号时，使用独立启动器：

```text
~/.cc-switch/codex-cli-launchers/codex-<name>.command
```

生成的启动器通过本地 bridge 路由，不会把 OAuth token 复制到 `auth.json`。

### 设置全局 Codex CLI 账号

只在工具直接调用默认 `codex` 命令、无法传入自定义命令时使用，例如 Desktop 集成、tmux/OMC shim。

BridgeDeck 会先备份，再只把选中账号的 `base_url` 写入 `~/.codex/config.toml`。不会写入 `access_token`、`refresh_token` 或 `id_token`。

## 本地 API 接入

BridgeDeck 暴露账号级本地路由。API key 是本地占位符，不是真实 OpenAI token。

```bash
OPENAI_API_KEY=sk-bridgedeck-local-placeholder
OPENAI_BASE_URL=http://127.0.0.1:8876/accounts/<account_id>/v1
```

OpenAI 兼容路由：

```text
POST /accounts/<account_id>/v1/responses
POST /accounts/<account_id>/v1/chat/completions
GET  /accounts/<account_id>/v1/models
```

Anthropic 兼容路由：

```text
POST /accounts/<account_id>/v1/messages
```

Anthropic 风格环境变量示例：

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8876/accounts/<account_id>/v1
ANTHROPIC_AUTH_TOKEN=local-bridge
ANTHROPIC_DEFAULT_HAIKU_MODEL=gpt-5.3-codex-spark
ANTHROPIC_DEFAULT_SONNET_MODEL=gpt-5.3-codex
ANTHROPIC_DEFAULT_OPUS_MODEL=gpt-5.5
CLAUDE_CODE_MAX_CONTEXT_TOKENS=272000
```

不要默认设置 `ANTHROPIC_MODEL`。只有你明确要把所有 Claude Code 主请求强制到某个模型时才设置它；留空时，Claude 的 `haiku` / `sonnet` / `opus` slot 路由才会有意义。

BridgeDeck 也会暴露桌面端安全的 Claude 风格模型别名。遇到客户端限制模型名时，可以用页面显示的别名；页面会同时显示“请求模型”和“实际路由模型”。

## 用量仪表盘

`使用详情` 页面读取 Local Codex Bridge 状态，并显示：

- 总请求数
- 总 Token
- 输入和输出 Token
- 缓存创建/写入 Token
- 缓存命中 Token
- 缓存未命中 Token
- 缓存命中率和未命中率
- Provider/账号标签
- 请求模型和实际路由模型
- 客户端来源，例如 Codex、Claude Code、Desktop、Hermes 或通用 API
- HTTP 状态和最近错误状态

BridgeDeck 只保留最近的本地事件。账号标识显示前会先脱敏。

## 读写哪些文件

BridgeDeck 会根据你点击的操作读取或写入这些本机文件：

```text
~/.cc-switch/cc-switch.db
~/.cc-switch/settings.json
~/.cc-switch/codex_oauth_auth.json
~/.cc-switch/codex-cli-launchers/*
~/.cc-switch/bridgedeck-backups/*
~/.cc-switch/bridgedeck-local-bridge-state.json
~/.codex/config.toml
~/.codex/.env
~/.codex-cli-*
```

写入本地配置前会先备份到：

```text
~/.cc-switch/bridgedeck-backups/
```

## 安全与隐私

- 默认只监听 localhost。
- 非本机监听必须显式传入 `--allow-remote`。
- 远程模式默认只读。
- 远程只读响应会脱敏账号 ID、邮箱、本地路径、代理凭据和 bridge 账号 URL。
- 远程模式下写入 API 和显示 token 需要额外传入 `--allow-remote-write`。
- API 请求需要本次启动生成的浏览器 token。
- 浏览器支持 Fetch Metadata 时会拒绝跨站请求。
- HTML 响应使用 CSP、防 iframe 嵌入、`no-store`、`nosniff` 和 referrer policy。
- `/api/data` 默认不返回完整 token，只有本地 UI 明确请求显示敏感信息时才会返回。

不要公开这些文件或真实环境截图：

```text
~/.cc-switch/codex_oauth_auth.json
~/.cc-switch/cc-switch.db
~/.codex/auth.json
~/.codex-cli-*/auth.json
包含账号 ID 或邮箱的截图
包含 token、账号 ID、邮箱、本地路径或代理凭据的日志
```

## 排障

| 问题 | 检查 |
| --- | --- |
| UI 一直加载 | 打开 `http://127.0.0.1:8899`，必要时只重启 UI；`8876` bridge 可以继续运行。 |
| 本地 API 返回 `404` | base URL 使用 `/accounts/<account_id>/v1`，并确认调用的是受支持的本地路由。 |
| 本地 API 返回 `401` | 在 BridgeDeck 或 CC Switch 重新授权账号，然后更新对应 Local Bridge Provider。 |
| 代理返回 `503` | 检查当前代理、CC Switch 服务和 Local Codex Bridge 状态；上游临时错误也可能表现为 `503`。 |
| Desktop 客户端拒绝模型名 | 使用 BridgeDeck 页面显示的模型别名，并确认实际路由模型正确。 |
| 额度或账号不一致 | 看状态矩阵和 Provider 不一致面板，然后重新授权或更新 Provider 绑定。 |

## 命令行参数

```text
--db PATH              cc-switch.db 路径
--settings PATH        settings.json 路径
--auth-store PATH      codex_oauth_auth.json 路径
--host HOST            监听地址，默认 127.0.0.1
--port PORT            监听端口，默认 8899
--allow-remote         允许非本机监听；默认只读且不能显示完整 token
--allow-remote-write   允许远程模式写入和显示完整 token
--local-bridge ACTION  不启动 UI，直接 start/stop/restart/status 8876
```

## 开发

本地检查：

```bash
python3 -m py_compile bridgedeck.py local_codex_bridge.py
python3 -m unittest discover -s tests
zsh -n run-bridgedeck.command
zsh -n package-bridgedeck-dmg.command
```

打包 macOS App 和 DMG：

```bash
chmod +x package-bridgedeck-dmg.command
./package-bridgedeck-dmg.command
shasum -a 256 dist/BridgeDeck.dmg
```

项目结构：

```text
bridgedeck.py                   本地网页应用和 API
local_codex_bridge.py           8876 账号级 bridge 服务
BridgeDeckLauncher.swift        macOS 原生 App 启动器
run-bridgedeck.command          源码启动脚本
package-bridgedeck-dmg.command  macOS App 和 DMG 打包脚本
README.md                       英文文档
README.zh-CN.md                 简体中文文档
SECURITY.md                     安全说明
CONTRIBUTING.md                 贡献说明
CHANGELOG.md                    变更记录
OPEN_SOURCE_CHECKLIST.md        发布检查清单
LICENSE                         PolyForm Noncommercial 1.0.0
COMMERCIAL.md                   商业授权说明
```

## 许可证

BridgeDeck 使用 PolyForm Noncommercial License 1.0.0 授权。

商业使用需要单独取得书面商业授权。见 `COMMERCIAL.md`。
