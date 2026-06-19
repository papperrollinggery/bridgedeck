[CmdletBinding()]
param(
  [string]$BridgeDeckDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$WslDistro = "",
  [string]$WslExe = "wsl.exe",
  [string]$PythonExe = "python",
  [string]$ProxyTargetHost = "127.0.0.1",
  [int]$ProxyTargetPort = 7897,
  [string]$RelayListenHost = "",
  [int]$RelayListenPort = 17897,
  [int]$BridgeDeckPort = 8899,
  [switch]$SkipRelay,
  [switch]$AllowLanRelay
)

$ErrorActionPreference = "Stop"

function Convert-ToWslPath([string]$Path) {
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  if ($resolved -notmatch "^[A-Za-z]:\\") {
    throw "Only drive-letter Windows paths are supported: $resolved"
  }
  $drive = $resolved.Substring(0, 1).ToLowerInvariant()
  $rest = $resolved.Substring(2).Replace("\", "/")
  return "/mnt/$drive$rest"
}

function Quote-WslShell([string]$Value) {
  return "'" + $Value.Replace("'", "'\''") + "'"
}

function Quote-WindowsArgument([string]$Value) {
  if ($Value -notmatch '[\s"]') {
    return $Value
  }
  return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

function Test-CommandLineArgument([string]$CommandLine, [string]$Name, [string]$Value) {
  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }
  $escapedName = [regex]::Escape($Name)
  $escapedValue = [regex]::Escape($Value)
  return $CommandLine -match "(^|\s)$escapedName\s+(`"$escapedValue`"|$escapedValue)(?=\s|$)"
}

function Get-RelayProcesses([string]$ListenHost, [int]$ListenPort, [string]$TargetHost = "", [int]$TargetPort = 0) {
  $processes = Get-CimInstance Win32_Process |
    Where-Object {
      $_.CommandLine -like "*windows-proxy-relay.py*" -and
      (Test-CommandLineArgument $_.CommandLine "--listen-host" $ListenHost) -and
      (Test-CommandLineArgument $_.CommandLine "--listen-port" ([string]$ListenPort))
    }

  if (-not [string]::IsNullOrWhiteSpace($TargetHost)) {
    $processes = $processes |
      Where-Object {
        (Test-CommandLineArgument $_.CommandLine "--target-host" $TargetHost) -and
        (Test-CommandLineArgument $_.CommandLine "--target-port" ([string]$TargetPort))
      }
  }

  return @($processes)
}

function Invoke-WslText([string]$Command) {
  $args = @()
  if (-not [string]::IsNullOrWhiteSpace($WslDistro)) {
    $args += @("-d", $WslDistro)
  }
  $args += @("sh", "-lc", $Command)
  $output = & $WslExe @args
  if ($LASTEXITCODE -ne 0) {
    throw "wsl.exe failed while running: $Command"
  }
  return (($output -join "`n").Trim())
}

if (-not (Test-Path -LiteralPath (Join-Path $BridgeDeckDir "bridgedeck.py"))) {
  throw "BridgeDeckDir does not contain bridgedeck.py: $BridgeDeckDir"
}

$wslBridgeDir = Convert-ToWslPath $BridgeDeckDir
$wslHome = Convert-ToWslPath $env:USERPROFILE
$wslScript = "$wslBridgeDir/scripts/windows/start-bridgedeck-wsl.sh"

if (-not $SkipRelay) {
  if ([string]::IsNullOrWhiteSpace($RelayListenHost)) {
    $gatewayCommand = "ip route show default | awk '{print `$3; exit}'"
    $RelayListenHost = Invoke-WslText $gatewayCommand
  }
  if ([string]::IsNullOrWhiteSpace($RelayListenHost)) {
    throw "Could not detect the WSL gateway host. Pass -RelayListenHost explicitly."
  }
  if (($RelayListenHost -eq "0.0.0.0" -or $RelayListenHost -eq "::") -and -not $AllowLanRelay) {
    throw "Refusing wildcard relay listener without -AllowLanRelay."
  }

  $relayScript = Join-Path $BridgeDeckDir "scripts\windows\windows-proxy-relay.py"
  $relayProcesses = Get-RelayProcesses -ListenHost $RelayListenHost -ListenPort $RelayListenPort
  $relayProcess = Get-RelayProcesses -ListenHost $RelayListenHost -ListenPort $RelayListenPort -TargetHost $ProxyTargetHost -TargetPort $ProxyTargetPort |
    Select-Object -First 1
  $staleRelayProcesses = @($relayProcesses |
    Where-Object {
      -not (
        (Test-CommandLineArgument $_.CommandLine "--target-host" $ProxyTargetHost) -and
        (Test-CommandLineArgument $_.CommandLine "--target-port" ([string]$ProxyTargetPort))
      )
    })

  if ($staleRelayProcesses.Count -gt 0) {
    foreach ($process in $staleRelayProcesses) {
      Stop-Process -Id $process.ProcessId -Force
    }
    Start-Sleep -Seconds 1
  }

  if (-not $relayProcess) {
    $relayArgs = @(
      $relayScript,
      "--listen-host", $RelayListenHost,
      "--listen-port", [string]$RelayListenPort,
      "--target-host", $ProxyTargetHost,
      "--target-port", [string]$ProxyTargetPort
    )
    if ($AllowLanRelay) {
      $relayArgs += "--allow-lan"
    }
    Start-Process -FilePath $PythonExe -ArgumentList (($relayArgs | ForEach-Object { Quote-WindowsArgument $_ }) -join " ") -WindowStyle Hidden
    Start-Sleep -Seconds 1
    $relayProcess = Get-RelayProcesses -ListenHost $RelayListenHost -ListenPort $RelayListenPort -TargetHost $ProxyTargetHost -TargetPort $ProxyTargetPort |
      Select-Object -First 1
    if (-not $relayProcess) {
      throw "Proxy relay failed to start: $RelayListenHost`:$RelayListenPort -> $ProxyTargetHost`:$ProxyTargetPort. Check Python, bind permissions, and whether another process owns the listen port."
    }
  }
}

$envParts = @(
  "BRIDGEDECK_ROOT=$(Quote-WslShell $wslBridgeDir)",
  "BRIDGEDECK_WINDOWS_HOME=$(Quote-WslShell $wslHome)",
  "BRIDGEDECK_PORT=$BridgeDeckPort"
)

if ($SkipRelay) {
  $envParts += "BRIDGEDECK_SKIP_PROXY=1"
} else {
  $envParts += "BRIDGEDECK_WINDOWS_PROXY_HOST=$(Quote-WslShell $RelayListenHost)"
  $envParts += "BRIDGEDECK_WINDOWS_PROXY_RELAY_PORT=$RelayListenPort"
}

$linuxCommand = ($envParts -join " ") + " bash " + (Quote-WslShell $wslScript)
$wslArgs = @()
if (-not [string]::IsNullOrWhiteSpace($WslDistro)) {
  $wslArgs += @("-d", $WslDistro)
}
$wslArgs += @("sh", "-lc", $linuxCommand)

Start-Process -FilePath $WslExe -ArgumentList (($wslArgs | ForEach-Object { Quote-WindowsArgument $_ }) -join " ") -WindowStyle Hidden
Start-Sleep -Seconds 5

try {
  $uri = "http://127.0.0.1:$BridgeDeckPort/"
  $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 8
  "BridgeDeck UI is running: $uri (HTTP $($response.StatusCode))"
  if (-not $SkipRelay) {
    "Proxy relay: http://$RelayListenHost`:$RelayListenPort -> $ProxyTargetHost`:$ProxyTargetPort"
  }
} catch {
  "BridgeDeck UI did not respond. Check WSL, proxy relay, and BridgeDeck logs."
  throw
}
