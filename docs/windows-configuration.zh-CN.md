# Windows 系统配置指南

本文档用于在 Windows 上通过 WSL 运行 BridgeDeck，并暴露本地 OpenAI/Anthropic 兼容接口。它只记录 BridgeDeck 相关配置，不包含任何浏览器扩展、第三方产品、个人账号、邮箱、token、API key 或订阅信息。

示例里的 `<Windows用户名>`、`<代理端口>`、`<account_id>` 都需要按本机环境替换。

## 目标结果

配置完成后应具备以下能力：

- BridgeDeck UI 可在 `http://127.0.0.1:8899/` 打开。
- BridgeDeck Local Bridge 可在 `http://127.0.0.1:8876/v1` 提供本地 API。
- 需要账号级隔离时，可使用 `http://127.0.0.1:8876/accounts/<account_id>/v1`。
- OpenAI 兼容客户端可调用 `/v1/responses`、`/v1/chat/completions`、`/v1/models`。
- Anthropic 兼容客户端可调用 `/v1/messages`。

BridgeDeck 在本地启动兼容服务：

```text
OpenAI/Anthropic-compatible client
-> http://127.0.0.1:8876/v1
-> BridgeDeck Local Bridge
-> ChatGPT/Codex 登录态
-> OpenAI/Codex 后端
```

Windows 上的 BridgeDeck Python 脚本依赖 Unix-only `fcntl`，建议通过 WSL 运行 BridgeDeck。WSL 访问 Windows 的 `127.0.0.1` 代理经常不通，因此仓库提供了 Windows 侧 TCP relay 和 WSL 启动脚本。

## 前置条件

需要准备：

- Windows 10/11。
- 已安装 WSL，例如 Ubuntu。
- WSL 内有 `python3`。
- Windows 内有 Python，用于运行本地 TCP relay。
- 已安装并可用的本机代理工具，例如 Clash Verge Rev 或 Mihomo。
- 已能正常使用 Codex Desktop 或 Codex CLI，或准备通过 BridgeDeck 设备授权登录。

## 仓库脚本

Windows/WSL 支持脚本位于：

```text
scripts/windows/Start-BridgeDeck.ps1
scripts/windows/start-bridgedeck-wsl.sh
scripts/windows/windows-proxy-relay.py
scripts/windows/Import-BridgeDeckCodexAuth.ps1
```

用途：

| 脚本 | 作用 |
| --- | --- |
| `Start-BridgeDeck.ps1` | Windows 一键启动入口：检测 WSL gateway、启动 relay、启动 BridgeDeck UI。 |
| `start-bridgedeck-wsl.sh` | WSL 内启动 BridgeDeck，设置 Windows HOME 和代理环境变量。 |
| `windows-proxy-relay.py` | 把 WSL 到 Windows gateway 的请求转发到 Windows 本机代理端口。 |
| `Import-BridgeDeckCodexAuth.ps1` | 高级兜底：显式确认后从 Codex auth 缓存初始化 BridgeDeck auth store。 |

`windows-proxy-relay.py` 默认拒绝 `0.0.0.0` 监听。正常路径由 `Start-BridgeDeck.ps1` 自动检测 WSL gateway 并绑定该地址，不需要开启 Clash/Mihomo 的 allow-lan。

## 1. 安装 BridgeDeck

克隆或下载 BridgeDeck 到：

```text
C:\Users\<Windows用户名>\tools\bridgedeck
```

在 WSL 中准备依赖并验证 Python 能编译：

```bash
cd "/mnt/c/Users/<Windows用户名>/tools/bridgedeck"
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install httpx
python3 -m py_compile bridgedeck.py local_codex_bridge.py scripts/windows/windows-proxy-relay.py
```

如果已用系统 Python 管理依赖，可以不建 `.venv`；`start-bridgedeck-wsl.sh` 会在存在 `.venv/bin/activate` 时自动加载它。

## 2. 启动 BridgeDeck

先确认 Windows 代理工具正在监听，例如 Clash/Mihomo mixed port `7897`、`7890` 或 `7899`。

查看当前代理监听端口：

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 7897,7890,7899,1087 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

以目标代理端口 `7897` 为例启动：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\scripts\windows\Start-BridgeDeck.ps1 -ProxyTargetPort 7897
```

成功后访问：

```text
http://127.0.0.1:8899/
```

该脚本会做三件事：

1. 从 WSL 读取默认网关地址。
2. 在 Windows 侧启动 relay：`http://<WSL默认网关>:17897 -> Windows 127.0.0.1:<代理端口>`。
3. 在 WSL 内启动 BridgeDeck，并让 UI 与 Local Bridge 使用同一条代理链路。

如果必须手动指定 WSL gateway：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\scripts\windows\Start-BridgeDeck.ps1 `
  -ProxyTargetPort 7897 `
  -RelayListenHost 172.xx.xx.1
```

不要把 `-RelayListenHost` 设成 `0.0.0.0`。如果明确要暴露到局域网，必须同时传 `-AllowLanRelay`，并先配置 Windows 防火墙只允许可信来源。

## 3. 初始化 BridgeDeck 账号

推荐使用方式 A。方式 B 只适合作为迁移或设备授权不可用时的本机兜底。

### 方式 A：BridgeDeck 设备授权

在 BridgeDeck UI 中生成 OpenAI 设备授权码，根据页面提示登录并授权。

注意：

- 如果页面提示“验证码应正好包含 6 个字符 / 代码必须仅包含数字”，通常是 OpenAI 登录或 MFA 页面，不是设备码输入框。
- 先完成账号登录、邮箱验证或 MFA，再进入设备授权码页面。
- 不要把 BridgeDeck 生成的设备码输入到 6 位数字 MFA 输入框。

### 方式 B：从本机 Codex 登录缓存初始化

该方式会读取：

```text
C:\Users\<Windows用户名>\.codex\auth.json
```

并把 refresh token 写入：

```text
C:\Users\<Windows用户名>\.cc-switch\bridgedeck-auth.json
```

这会让 BridgeDeck 拥有自己的 refresh fallback。OpenAI refresh token 会轮换；如果 Codex Desktop、AiMaMi 和 BridgeDeck 同时刷新同一账号，可能触发 `refresh_token_reused`。只在可信本机、明确接受该风险时运行：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\scripts\windows\Import-BridgeDeckCodexAuth.ps1 -ConfirmRefreshTokenCopy
```

脚本不会打印 token；如果目标 auth store 已存在，会先创建 `bridgedeck-auth.json.backup-<timestamp>`。默认不会覆盖已有 `default_account_id`；如果要把导入账号设为默认账号，额外传入 `-SetDefault`。

## 4. 启动 Local Bridge

打开 BridgeDeck UI：

```text
http://127.0.0.1:8899/
```

在 Services / Local Bridge 区域点击启动或重启 Local Bridge。

也可以用 BridgeDeck CLI：

```bash
cd "/mnt/c/Users/<Windows用户名>/tools/bridgedeck"
HOME="/mnt/c/Users/<Windows用户名>" python3 bridgedeck.py --local-bridge start --force-local-bridge
```

## 5. 验证接口

验证 UI：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8899/' -TimeoutSec 8 |
  Select-Object -ExpandProperty StatusCode
```

期望输出：

```text
200
```

验证 models：

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8876/v1/models' `
  -Headers @{ Authorization = 'Bearer local-bridge' } `
  -TimeoutSec 10 |
  Select-Object -ExpandProperty StatusCode
```

期望输出：

```text
200
```

验证文本调用：

```powershell
$body = @{
  model = 'gpt-5.5'
  messages = @(@{ role = 'user'; content = 'Reply with OK only.' })
  max_tokens = 16
  stream = $false
} | ConvertTo-Json -Depth 6

Invoke-WebRequest -UseBasicParsing `
  -Method Post `
  -Uri 'http://127.0.0.1:8876/v1/chat/completions' `
  -Headers @{ Authorization = 'Bearer local-bridge'; 'Content-Type' = 'application/json' } `
  -Body $body `
  -TimeoutSec 120 |
  Select-Object -ExpandProperty Content
```

期望返回 JSON，内容里有 assistant 回复。

## 常见问题

### about:blank 没跳到授权页

通常是 BridgeDeck 后端没有拿到设备授权 URL。检查：

- BridgeDeck UI 是否 200。
- WSL 是否能通过 relay 访问代理。
- 代理节点是否支持 OpenAI / ChatGPT / Codex。

### OpenAI 页面要求 6 位数字

这是登录或 MFA 验证页面，不是 BridgeDeck 设备码输入页。先完成 OpenAI 账号登录，再进入设备授权页面。

### `/v1/models` 通，但 `/v1/chat/completions` 失败

检查：

- `C:\Users\<Windows用户名>\.cc-switch\bridgedeck-auth.json` 是否存在。
- 该 JSON 是否为 UTF-8 无 BOM。
- auth store 是否有 `default_account_id`。
- Local Bridge 日志：

```text
C:\Users\<Windows用户名>\.cc-switch\bridgedeck-local-bridge.log
```

如果日志出现：

```text
Unexpected UTF-8 BOM
```

用 UTF-8 无 BOM 重写 `bridgedeck-auth.json`，或重新运行 `Import-BridgeDeckCodexAuth.ps1 -ConfirmRefreshTokenCopy`。如果要切换默认账号，额外传入 `-SetDefault`。

### WSL 里连不上 Windows 代理

不要直接在 WSL 里连 `127.0.0.1:<代理端口>`。应使用：

```bash
ip route show default
```

取默认网关，例如：

```text
default via 172.xx.xx.1 dev eth0
```

然后通过：

```text
http://172.xx.xx.1:17897
```

访问 Windows 侧 relay。`Start-BridgeDeck.ps1` 会自动设置 `CODEX_BRIDGE_UPSTREAM_PROXY` 指向这个地址。

### 不想修改 Clash Verge 设置

使用仓库里的 `scripts/windows/windows-proxy-relay.py` 方案即可。它不要求把 Clash/Mihomo 改成 allow-lan 或 `0.0.0.0` 监听。

## 重启后的恢复步骤

每次重启电脑后，按顺序执行：

1. 启动代理工具，确认 Windows 上 `127.0.0.1:<代理端口>` 可用。
2. 启动 BridgeDeck：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\scripts\windows\Start-BridgeDeck.ps1 -ProxyTargetPort <代理端口>
```

3. 打开：

```text
http://127.0.0.1:8899/
```

4. 确认 Local Bridge 运行。
5. 测试：

```text
http://127.0.0.1:8876/v1/models
```
