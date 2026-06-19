# Windows 系统配置指南

本文档用于在 Windows 上通过 WSL 运行 BridgeDeck，并暴露本地 OpenAI/Anthropic 兼容接口。它只记录 BridgeDeck 相关配置，不包含任何浏览器扩展、第三方产品、个人账号、邮箱、token、API key 或订阅信息。

所有示例里的 `<Windows用户名>`、`<WSL用户名>`、`<代理端口>` 都需要按本机环境替换。

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

Windows 上的 BridgeDeck Python 脚本依赖 Unix-only `fcntl`，建议通过 WSL 运行 BridgeDeck。WSL 访问 Windows 的 `127.0.0.1` 代理经常不通，因此推荐使用一个 Windows 侧轻量 TCP relay，让 WSL 通过默认网关访问 Windows 代理。

## 前置条件

需要准备：

- Windows 10/11。
- 已安装 WSL，例如 Ubuntu。
- WSL 内有 `python3`，并能导入 BridgeDeck 依赖。
- Windows 内有 Python，用于运行本地 TCP relay。
- 已安装并可用的本机代理工具，例如 Clash Verge Rev 或 Mihomo。
- 已能正常使用 Codex Desktop 或 Codex CLI，且本机存在 `.codex/auth.json` 登录缓存。

## 目录约定

建议使用以下目录。实际用户名请替换为本机用户名。

```text
C:\Users\<Windows用户名>\tools\bridgedeck
C:\Users\<Windows用户名>\.codex\auth.json
C:\Users\<Windows用户名>\.cc-switch\bridgedeck-auth.json
```

在 WSL 中，Windows 用户目录一般映射为：

```text
/mnt/c/Users/<Windows用户名>
```

## 1. 安装 BridgeDeck

克隆或下载 BridgeDeck 到：

```text
C:\Users\<Windows用户名>\tools\bridgedeck
```

至少需要以下文件：

```text
bridgedeck.py
local_codex_bridge.py
README.md
README.zh-CN.md
AGENTS.md
LICENSE
```

在 WSL 中验证 Python 能编译：

```bash
cd "/mnt/c/Users/<Windows用户名>/tools/bridgedeck"
python3 -m py_compile bridgedeck.py local_codex_bridge.py
```

如果缺少依赖，按 BridgeDeck README 安装。常见依赖包括 `httpx`。

## 2. 不修改 Clash Verge 设置的代理方案

如果代理工具只监听 Windows 的 `127.0.0.1:<代理端口>`，WSL 里直接访问 `127.0.0.1:<代理端口>` 通常不通。

推荐做法：不改 Clash Verge 设置，在 Windows 侧启动一个 TCP relay：

```text
WSL -> http://<WSL默认网关>:17897 -> Windows 127.0.0.1:<代理端口>
```

常见 Clash/Mihomo mixed port 是 `7897`、`7890` 或 `7899`。以 `7897` 为例。

在 `C:\Users\<Windows用户名>\tools\bridgedeck\windows-proxy-relay.py` 创建：

```python
#!/usr/bin/env python3
"""Tiny TCP relay for WSL -> Windows loopback proxy access."""
from __future__ import annotations

import argparse
import socket
import threading
import time

BUFFER_SIZE = 65536


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client: socket.socket, target_host: str, target_port: int) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=10)
        for sock in (client, upstream):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        left = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
        right = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
        left.start()
        right.start()
        left.join()
        right.join()
    except OSError:
        pass
    finally:
        for sock in (client, upstream):
            if sock is None:
                continue
            try:
                sock.close()
            except OSError:
                pass


def serve(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((listen_host, listen_port))
    server.listen(128)
    print(
        f"BridgeDeck proxy relay listening on {listen_host}:{listen_port} "
        f"-> {target_host}:{target_port}",
        flush=True,
    )
    while True:
        try:
            client, _addr = server.accept()
        except OSError:
            time.sleep(0.2)
            continue
        threading.Thread(target=handle, args=(client, target_host, target_port), daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=17897)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=7897)
    args = parser.parse_args()
    serve(args.listen_host, args.listen_port, args.target_host, args.target_port)


if __name__ == "__main__":
    main()
```

如果你的代理端口不是 `7897`，把 `--target-port` 换成本机实际端口。

查看当前代理监听端口：

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 7897,7890,7899,1087 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

## 3. 创建 BridgeDeck WSL 启动脚本

在 `C:\Users\<Windows用户名>\tools\bridgedeck\start-bridgedeck-wsl.sh` 创建：

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "/mnt/c/Users/<Windows用户名>/tools/bridgedeck"
export HOME="/mnt/c/Users/<Windows用户名>"

# 如果 httpx 等依赖装在用户 site-packages，可按实际 WSL 用户名调整。
# 不需要时可以删掉这一行。
export PYTHONPATH="/home/<WSL用户名>/.local/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}"

proxy_host="$(ip route show default | awk '{print $3; exit}')"
if [[ -n "${proxy_host}" ]]; then
  proxy_port="${BRIDGEDECK_WINDOWS_PROXY_RELAY_PORT:-17897}"
  proxy_url="http://${proxy_host}:${proxy_port}"
  export HTTP_PROXY="${proxy_url}"
  export HTTPS_PROXY="${proxy_url}"
  export ALL_PROXY="${proxy_url}"
  export http_proxy="${proxy_url}"
  export https_proxy="${proxy_url}"
  export all_proxy="${proxy_url}"
  export CODEX_BRIDGE_UPSTREAM_PROXY="${proxy_url}"
  export NO_PROXY="127.0.0.1,localhost,::1"
  export no_proxy="${NO_PROXY}"
fi

exec python3 bridgedeck.py --host 127.0.0.1 --port 8899
```

要点：

- `HOME` 必须指向 Windows 用户目录的 WSL 路径，这样 BridgeDeck 才会读写 Windows 下的 `.codex`、`.cc-switch`。
- `proxy_host` 使用 WSL 默认网关，不要写死 `127.0.0.1`。
- `CODEX_BRIDGE_UPSTREAM_PROXY` 让 Local Bridge 也走同一条代理链路。

## 4. 创建 Windows 一键启动脚本

在 `C:\Users\<Windows用户名>\tools\bridgedeck\Start-BridgeDeck.ps1` 创建：

```powershell
$ErrorActionPreference = "Stop"

$relayScript = "C:\Users\<Windows用户名>\tools\bridgedeck\windows-proxy-relay.py"
$relayProcess = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*windows-proxy-relay.py*" }

if (-not $relayProcess) {
  Start-Process -FilePath "python" -ArgumentList @(
    $relayScript,
    "--listen-host", "0.0.0.0",
    "--listen-port", "17897",
    "--target-host", "127.0.0.1",
    "--target-port", "7897"
  ) -WindowStyle Hidden
  Start-Sleep -Seconds 1
}

$script = "/mnt/c/Users/<Windows用户名>/tools/bridgedeck/start-bridgedeck-wsl.sh"
Start-Process -FilePath "wsl.exe" -ArgumentList @("bash", $script) -WindowStyle Hidden
Start-Sleep -Seconds 5

try {
  $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8899/" -TimeoutSec 8
  "BridgeDeck UI is running: http://127.0.0.1:8899/ (HTTP $($response.StatusCode))"
} catch {
  "BridgeDeck UI did not respond on http://127.0.0.1:8899/. Check WSL and BridgeDeck logs."
  throw
}
```

启动：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\Start-BridgeDeck.ps1
```

成功后访问：

```text
http://127.0.0.1:8899/
```

## 5. 初始化 BridgeDeck 账号

有两种方式。

### 方式 A：BridgeDeck 设备授权

在 BridgeDeck UI 中生成 OpenAI 设备授权码，根据页面提示登录并授权。

注意：

- 如果页面提示“验证码应正好包含 6 个字符 / 代码必须仅包含数字”，通常是 OpenAI 登录或 MFA 页面，不是设备码输入框。
- 先完成账号登录、邮箱验证或 MFA，再进入设备授权码页面。
- 不要把 BridgeDeck 生成的设备码输入到 6 位数字 MFA 输入框。

### 方式 B：从本机 Codex 登录缓存初始化

如果本机已经能使用 Codex Desktop 或 Codex CLI，通常会存在：

```text
C:\Users\<Windows用户名>\.codex\auth.json
```

可以从该文件初始化 BridgeDeck 的 auth store。以下脚本不会打印 token，但会在本机读取并复制 refresh token 到 BridgeDeck 自己的 auth store。只在可信本机运行。

```powershell
$ErrorActionPreference = 'Stop'

$codexAuthPath = 'C:\Users\<Windows用户名>\.codex\auth.json'
$bridgeAuthPath = 'C:\Users\<Windows用户名>\.cc-switch\bridgedeck-auth.json'

$codexAuth = Get-Content -LiteralPath $codexAuthPath -Encoding UTF8 -Raw | ConvertFrom-Json
$accountId = [string]$codexAuth.tokens.account_id
$refresh = [string]$codexAuth.tokens.refresh_token

if ([string]::IsNullOrWhiteSpace($accountId) -or [string]::IsNullOrWhiteSpace($refresh)) {
  throw 'Codex auth.json lacks account_id or refresh_token'
}

$email = ''
try {
  $jwt = [string]$codexAuth.tokens.id_token
  if ([string]::IsNullOrWhiteSpace($jwt)) { $jwt = [string]$codexAuth.tokens.access_token }
  $parts = $jwt.Split('.')
  if ($parts.Length -ge 2) {
    $payload = $parts[1].Replace('-', '+').Replace('_', '/')
    while (($payload.Length % 4) -ne 0) { $payload += '=' }
    $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
    $email = [string]$json.email
  }
} catch {
  $email = ''
}

if (Test-Path -LiteralPath $bridgeAuthPath) {
  $backup = Join-Path (Split-Path -Parent $bridgeAuthPath) ('bridgedeck-auth.json.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  Copy-Item -LiteralPath $bridgeAuthPath -Destination $backup -Force
  $existing = Get-Content -LiteralPath $bridgeAuthPath -Encoding UTF8 -Raw | ConvertFrom-Json
} else {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bridgeAuthPath) | Out-Null
  $existing = [pscustomobject]@{ version = 1; accounts = [pscustomobject]@{}; default_account_id = '' }
}

$accounts = @{}
if ($existing.accounts) {
  foreach ($prop in $existing.accounts.PSObject.Properties) {
    $accounts[$prop.Name] = $prop.Value
  }
}

$accounts[$accountId] = [ordered]@{
  account_id = $accountId
  email = $email
  refresh_token = $refresh
  authenticated_at = [int][double]::Parse((Get-Date -UFormat %s))
  source = 'codex_auth_import'
}

$outAccounts = [ordered]@{}
foreach ($key in $accounts.Keys) {
  $outAccounts[$key] = $accounts[$key]
}

$out = [ordered]@{
  version = 1
  accounts = $outAccounts
  default_account_id = $accountId
}

# PowerShell 5 的 UTF8 默认带 BOM；Local Bridge 不接受 BOM，所以必须无 BOM 写入。
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($bridgeAuthPath, ($out | ConvertTo-Json -Depth 8), $utf8NoBom)

'BridgeDeck auth store initialized without printing tokens.'
```

## 6. 启动 Local Bridge

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

## 7. 验证接口

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

验证图片调用：

```powershell
@'
import base64, json, struct, zlib, urllib.request, urllib.error

def chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

raw = b'\x00\xff\x00\x00'
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
data_url = 'data:image/png;base64,' + base64.b64encode(png).decode()

body = {
    'model': 'gpt-5.5',
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': 'What is the dominant color in this image? Reply with one word.'},
            {'type': 'image_url', 'image_url': {'url': data_url}},
        ],
    }],
    'max_tokens': 20,
    'stream': False,
}

req = urllib.request.Request(
    'http://127.0.0.1:8876/v1/chat/completions',
    data=json.dumps(body).encode('utf-8'),
    headers={'Authorization': 'Bearer local-bridge', 'Content-Type': 'application/json'},
    method='POST',
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        print(resp.status)
        print(resp.read().decode('utf-8'))
except urllib.error.HTTPError as exc:
    print(exc.code)
    print(exc.read().decode('utf-8', 'replace'))
'@ | python -
```

期望第一行是：

```text
200
```

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

用 UTF-8 无 BOM 重写 `bridgedeck-auth.json`。

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

访问 Windows 侧 relay。

### 不想修改 Clash Verge 设置

使用本文的 `windows-proxy-relay.py` 方案即可。它不要求把 Clash/Mihomo 改成 allow-lan 或 `0.0.0.0` 监听。

## 重启后的恢复步骤

每次重启电脑后，按顺序执行：

1. 启动代理工具，确认 Windows 上 `127.0.0.1:<代理端口>` 可用。
2. 启动 BridgeDeck：

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\<Windows用户名>\tools\bridgedeck\Start-BridgeDeck.ps1
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
