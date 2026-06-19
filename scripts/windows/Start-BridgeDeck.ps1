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
  [switch]$AllowWslGatewayRelayHost,
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

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds = 1000) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Test-WildcardHost([string]$HostName) {
  return @("0", "0.0.0.0", "::") -contains $HostName
}

function Test-LoopbackHost([string]$HostName) {
  if ([string]::IsNullOrWhiteSpace($HostName)) {
    return $false
  }
  if ($HostName -eq "localhost") {
    return $true
  }
  try {
    $addresses = [System.Net.Dns]::GetHostAddresses($HostName)
  } catch {
    return $false
  }
  if ($addresses.Count -eq 0) {
    return $false
  }
  foreach ($address in $addresses) {
    if (-not [System.Net.IPAddress]::IsLoopback($address)) {
      return $false
    }
  }
  return $true
}

function Wait-RelayReady([string]$ListenHost, [int]$ListenPort, [string]$TargetHost, [int]$TargetPort) {
  for ($attempt = 0; $attempt -lt 10; $attempt++) {
    $process = Get-RelayProcesses -ListenHost $ListenHost -ListenPort $ListenPort -TargetHost $TargetHost -TargetPort $TargetPort |
      Select-Object -First 1
    if ($process -and (Test-TcpPort -HostName $ListenHost -Port $ListenPort -TimeoutMilliseconds 500)) {
      return $process
    }
    Start-Sleep -Milliseconds 500
  }
  return $null
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
  $relayListenHostWasAutoDetected = $false
  $detectedGatewayHost = ""
  $gatewayCommand = "ip route show default | awk '{print `$3; exit}'"
  try {
    $detectedGatewayHost = Invoke-WslText $gatewayCommand
  } catch {
    $detectedGatewayHost = ""
  }
  if ([string]::IsNullOrWhiteSpace($RelayListenHost)) {
    $RelayListenHost = $detectedGatewayHost
    $relayListenHostWasAutoDetected = $true
  }
  if ([string]::IsNullOrWhiteSpace($RelayListenHost)) {
    throw "Could not detect the WSL gateway host. Pass -RelayListenHost explicitly."
  }
  $relayListenHostIsDetectedGateway = (
    -not [string]::IsNullOrWhiteSpace($detectedGatewayHost) -and
    $RelayListenHost -eq $detectedGatewayHost
  )
  $relayListenHostIsExplicitGateway = (
    $AllowWslGatewayRelayHost -and
    -not $relayListenHostWasAutoDetected -and
    -not (Test-WildcardHost $RelayListenHost)
  )
  if ((Test-WildcardHost $RelayListenHost) -and -not $AllowLanRelay) {
    throw "Refusing wildcard relay listener without -AllowLanRelay."
  }
  if (-not $AllowLanRelay -and -not $relayListenHostIsDetectedGateway -and -not $relayListenHostIsExplicitGateway -and -not (Test-LoopbackHost $RelayListenHost)) {
    throw "Refusing non-loopback relay listener without -AllowLanRelay unless it matches the detected WSL gateway. Pass -AllowWslGatewayRelayHost for a manual WSL gateway override."
  }

  $relayScript = Join-Path $BridgeDeckDir "scripts\windows\windows-proxy-relay.py"
  if (-not (Test-TcpPort -HostName $ProxyTargetHost -Port $ProxyTargetPort -TimeoutMilliseconds 1000)) {
    throw "Proxy target is not reachable: $ProxyTargetHost`:$ProxyTargetPort. Start the Windows proxy or pass the correct -ProxyTargetHost/-ProxyTargetPort."
  }
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
    } elseif ($relayListenHostWasAutoDetected -or $relayListenHostIsDetectedGateway -or $relayListenHostIsExplicitGateway) {
      $relayArgs += @("--allow-host", $RelayListenHost)
    }
    Start-Process -FilePath $PythonExe -ArgumentList (($relayArgs | ForEach-Object { Quote-WindowsArgument $_ }) -join " ") -WindowStyle Hidden
    Start-Sleep -Seconds 1
  }
  $relayProcess = Wait-RelayReady -ListenHost $RelayListenHost -ListenPort $RelayListenPort -TargetHost $ProxyTargetHost -TargetPort $ProxyTargetPort
  if (-not $relayProcess) {
    throw "Proxy relay is not reachable: $RelayListenHost`:$RelayListenPort -> $ProxyTargetHost`:$ProxyTargetPort. Check Python, bind permissions, and whether another process owns the listen port."
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
