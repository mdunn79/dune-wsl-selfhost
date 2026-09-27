#Requires -RunAsAdministrator
# Install the LAN redirector on the GAMING PC (not the Dune host).
#
# Default: hidden Scheduled Task at logon (this Windows user, elevated).
# Optional: -Service  (WinSW + Windows service, LocalSystem, delayed auto-start.
#           Use this when the person who plays is not a daily Administrator.)

param(
    [string]$LanIp = "",
    [string]$PublicIp = "auto",
    [switch]$Service
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = "DuneLanRedirect"
$svcId = "DuneLanRedirect"
$cfgPath = Join-Path $here "dune-client.config.ps1"
$example = Join-Path $here "dune-client.config.example.ps1"
$startPs1 = Join-Path $here "Start-DuneLanRedirect.ps1"

function Test-Ipv4([string]$Ip) {
    return $Ip -match '^\d{1,3}(\.\d{1,3}){3}$'
}

if (-not (Test-Path $startPs1)) { throw "Missing $startPs1" }

if (-not (Test-Path $cfgPath)) {
    if (-not (Test-Path $example)) { throw "Missing $example" }
    if ([string]::IsNullOrWhiteSpace($LanIp)) {
        throw "Copy dune-client.config.example.ps1 to dune-client.config.ps1 and set LanIp, or pass -LanIp."
    }
    $pub = $PublicIp
    if ([string]::IsNullOrWhiteSpace($pub)) { $pub = "auto" }
    @"
@{
    LanIp    = "$LanIp"
    PublicIp = "$pub"
}
"@ | Set-Content -Path $cfgPath -Encoding ASCII
    Write-Host "Wrote $cfgPath"
} elseif (-not [string]::IsNullOrWhiteSpace($LanIp)) {
    $pub = $PublicIp
    if ([string]::IsNullOrWhiteSpace($pub)) { $pub = "auto" }
    @"
@{
    LanIp    = "$LanIp"
    PublicIp = "$pub"
}
"@ | Set-Content -Path $cfgPath -Encoding ASCII
    Write-Host "Updated $cfgPath"
}

$cfg = Get-Content -Raw $cfgPath | Invoke-Expression
$LanIp = [string]$cfg.LanIp
if (-not (Test-Ipv4 $LanIp)) { throw "dune-client.config.ps1 LanIp must be dotted IPv4" }

$mine = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress)
if ($mine -contains $LanIp) {
    throw "LanIp $LanIp is this PC. Install on the gaming PC, not the Dune host."
}

function Unregister-RedirectTask {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Uninstall-RedirectService {
    $exe = Join-Path $here "$svcId.exe"
    if (Test-Path $exe) {
        & $exe stop 2>$null | Out-Null
        & $exe uninstall 2>$null | Out-Null
    }
    if (Get-Service -Name $svcId -ErrorAction SilentlyContinue) {
        Stop-Service -Name $svcId -Force -ErrorAction SilentlyContinue
        sc.exe delete $svcId | Out-Null
    }
}

if ($Service) {
    Unregister-RedirectTask
    $winsw = Join-Path $here "$svcId.exe"
    if (-not (Test-Path $winsw)) {
        Write-Host "Downloading WinSW (MIT) for the Windows service wrapper..."
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" -OutFile $winsw
    }
    $xml = Join-Path $here "$svcId.xml"
    $ps = (Get-Command powershell.exe).Source
    @"
<service>
  <id>$svcId</id>
  <name>Dune LAN Redirect</name>
  <description>Rewrites Funcom public listing IP to the Dune host LAN address on this PC.</description>
  <executable>$ps</executable>
  <arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$startPs1" -Quiet -WatchDune</arguments>
  <workingdirectory>$here</workingdirectory>
  <logpath>$here\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>1024</sizeThreshold>
    <keepFiles>4</keepFiles>
  </log>
  <onfailure action="restart" delay="10 sec"/>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
</service>
"@ | Set-Content -Path $xml -Encoding UTF8
    New-Item -ItemType Directory -Force -Path (Join-Path $here "logs") | Out-Null
    & $winsw uninstall 2>$null | Out-Null
    & $winsw install
    if ($LASTEXITCODE -ne 0) { throw "WinSW install failed ($LASTEXITCODE)" }
    & $winsw start
    Write-Host "Service $svcId installed (delayed auto-start). Log: $here\logs and %LOCALAPPDATA%\DuneLanRedirect\redirect.log"
    Write-Host "Uninstall: .\Uninstall-DuneLanRedirect.ps1"
    return
}

Uninstall-RedirectService
$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startPs1`" -Quiet -WatchDune"
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Scheduled task $taskName installed (at logon, hidden, this user). Log: $env:LOCALAPPDATA\DuneLanRedirect\redirect.log"
Write-Host "Uninstall: .\Uninstall-DuneLanRedirect.ps1"
Write-Host "Non-admin play account: re-run with -Service"
