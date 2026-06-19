[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$CodexAuthPath = (Join-Path $env:USERPROFILE ".codex\auth.json"),
  [string]$BridgeAuthPath = (Join-Path $env:USERPROFILE ".cc-switch\bridgedeck-auth.json"),
  [switch]$ConfirmRefreshTokenCopy
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRefreshTokenCopy) {
  throw "Refusing to copy a refresh_token without -ConfirmRefreshTokenCopy."
}

function Get-JwtEmail([string]$Jwt) {
  if ([string]::IsNullOrWhiteSpace($Jwt)) {
    return ""
  }
  try {
    $parts = $Jwt.Split(".")
    if ($parts.Length -lt 2) {
      return ""
    }
    $payload = $parts[1].Replace("-", "+").Replace("_", "/")
    while (($payload.Length % 4) -ne 0) {
      $payload += "="
    }
    $json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
    return [string]$json.email
  } catch {
    return ""
  }
}

if (-not (Test-Path -LiteralPath $CodexAuthPath)) {
  throw "Codex auth file not found: $CodexAuthPath"
}

$codexAuth = Get-Content -LiteralPath $CodexAuthPath -Encoding UTF8 -Raw | ConvertFrom-Json
$accountId = [string]$codexAuth.tokens.account_id
$refresh = [string]$codexAuth.tokens.refresh_token

if ([string]::IsNullOrWhiteSpace($accountId) -or [string]::IsNullOrWhiteSpace($refresh)) {
  throw "Codex auth.json lacks account_id or refresh_token."
}

$jwt = [string]$codexAuth.tokens.id_token
if ([string]::IsNullOrWhiteSpace($jwt)) {
  $jwt = [string]$codexAuth.tokens.access_token
}
$email = Get-JwtEmail $jwt

if ($PSCmdlet.ShouldProcess($BridgeAuthPath, "copy Codex refresh_token into BridgeDeck auth store")) {
  $bridgeDir = Split-Path -Parent $BridgeAuthPath
  if (-not (Test-Path -LiteralPath $bridgeDir)) {
    New-Item -ItemType Directory -Force -Path $bridgeDir | Out-Null
  }

  if (Test-Path -LiteralPath $BridgeAuthPath) {
    $backup = Join-Path $bridgeDir ("bridgedeck-auth.json.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    Copy-Item -LiteralPath $BridgeAuthPath -Destination $backup -Force
    $existing = Get-Content -LiteralPath $BridgeAuthPath -Encoding UTF8 -Raw | ConvertFrom-Json
  } else {
    $backup = ""
    $existing = [pscustomobject]@{ version = 1; accounts = [pscustomobject]@{}; default_account_id = "" }
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
    authenticated_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    source = "codex_auth_import"
  }

  $outAccounts = [ordered]@{}
  foreach ($key in ($accounts.Keys | Sort-Object)) {
    $outAccounts[$key] = $accounts[$key]
  }

  $out = [ordered]@{
    version = 1
    accounts = $outAccounts
    default_account_id = $accountId
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($BridgeAuthPath, ($out | ConvertTo-Json -Depth 8), $utf8NoBom)

  "BridgeDeck auth store initialized without printing tokens."
  if ($backup) {
    "Backup written: $backup"
  }
}
