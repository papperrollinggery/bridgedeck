[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$CodexAuthPath = (Join-Path $env:USERPROFILE ".codex\auth.json"),
  [string]$BridgeAuthPath = (Join-Path $env:USERPROFILE ".cc-switch\bridgedeck-auth.json"),
  [switch]$ConfirmRefreshTokenCopy,
  [switch]$SetDefault
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRefreshTokenCopy) {
  throw "Refusing to copy a refresh_token without -ConfirmRefreshTokenCopy."
}

function Get-JwtPayload([string]$Jwt) {
  if ([string]::IsNullOrWhiteSpace($Jwt)) {
    return [pscustomobject]@{}
  }
  try {
    $parts = $Jwt.Split(".")
    if ($parts.Length -lt 2) {
      return [pscustomobject]@{}
    }
    $payload = $parts[1].Replace("-", "+").Replace("_", "/")
    while (($payload.Length % 4) -ne 0) {
      $payload += "="
    }
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
  } catch {
    return [pscustomobject]@{}
  }
}

function Get-JwtAccountId([object]$Payload) {
  $auth = $Payload."https://api.openai.com/auth"
  $accountId = ""
  if ($auth) {
    $accountId = [string]$auth.chatgpt_account_id
  }
  if ([string]::IsNullOrWhiteSpace($accountId)) {
    $accountId = [string]$Payload.chatgpt_account_id
  }
  return $accountId
}

function Get-JwtEmail([object]$Payload) {
  $profile = $Payload."https://api.openai.com/profile"
  $email = ""
  if ($profile) {
    $email = [string]$profile.email
  }
  if ([string]::IsNullOrWhiteSpace($email)) {
    $email = [string]$Payload.email
  }
  return $email
}

if (-not (Test-Path -LiteralPath $CodexAuthPath)) {
  throw "Codex auth file not found: $CodexAuthPath"
}

$codexAuth = Get-Content -LiteralPath $CodexAuthPath -Encoding UTF8 -Raw | ConvertFrom-Json
$accountId = [string]$codexAuth.tokens.account_id
$refresh = [string]$codexAuth.tokens.refresh_token
$idTokenPayload = Get-JwtPayload ([string]$codexAuth.tokens.id_token)
$accessTokenPayload = Get-JwtPayload ([string]$codexAuth.tokens.access_token)
if ([string]::IsNullOrWhiteSpace($accountId)) {
  $accountId = Get-JwtAccountId $idTokenPayload
}
if ([string]::IsNullOrWhiteSpace($accountId)) {
  $accountId = Get-JwtAccountId $accessTokenPayload
}
$email = Get-JwtEmail $idTokenPayload
if ([string]::IsNullOrWhiteSpace($email)) {
  $email = Get-JwtEmail $accessTokenPayload
}

if ([string]::IsNullOrWhiteSpace($accountId) -or [string]::IsNullOrWhiteSpace($refresh)) {
  throw "Codex auth.json lacks account_id or refresh_token."
}

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

  $defaultAccountId = [string]$existing.default_account_id
  if ($SetDefault -or [string]::IsNullOrWhiteSpace($defaultAccountId)) {
    $defaultAccountId = $accountId
  }

  $out = [ordered]@{
    version = 1
    accounts = $outAccounts
    default_account_id = $defaultAccountId
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($BridgeAuthPath, ($out | ConvertTo-Json -Depth 8), $utf8NoBom)

  "BridgeDeck auth store initialized without printing tokens."
  if ($defaultAccountId -eq $accountId) {
    "Imported account is the default account."
  } else {
    "Existing default account preserved. Re-run with -SetDefault to switch defaults."
  }
  if ($backup) {
    "Backup written: $backup"
  }
}
