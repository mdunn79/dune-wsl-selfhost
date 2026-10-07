# 5-minute join/admin health. No Steam, depot, advertise, FLS, or wsl --shutdown.
# Map pods missing: dune-ensure-runtime.sh only. Not Ready with pods present: log only.
# WAN down: local binds (and runtime if pods are gone). Skip while Restart-DuneBattlegroup.ps1 is running.
# Install: .\Install-DuneScheduledHealth.ps1   Log: repair-dune-health.log

$ErrorActionPreference = "Stop"
$LogFile = Join-Path $PSScriptRoot "repair-dune-health.log"
$LockFile = Join-Path $PSScriptRoot "repair-dune-health.lock"
$WslDistro = "Ubuntu"
$LanIp = ""
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $WslDistro = [string]$cfg.Distro }
    if ($cfg.LanIp) { $LanIp = [string]$cfg.LanIp.Trim() }
}

function Write-Log([string]$Message) {
    $clean = ([string]$Message) -replace '\x1b\[[0-9;]*m', '' -replace "`r", "" -replace "`n", ""
    if ([string]::IsNullOrWhiteSpace($clean)) { return }
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $clean
    Add-Content -Path $LogFile -Value $line
    [Console]::WriteLine($line)
}

function Test-WanUp {
    foreach ($hostAddr in @("1.1.1.1", "8.8.8.8")) {
        $client = $null
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect($hostAddr, 443, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(2000, $false) -and $client.Connected) {
                [void]$client.EndConnect($iar)
                return $true
            }
        } catch {
        } finally {
            if ($client) { $client.Close() }
        }
    }
    return $false
}

$lockStream = $null
try {
    $lockStream = [System.IO.File]::Open($LockFile, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    Write-Log "health already running; skip"
    return
}

try {
    Write-Log "=== Dune health begin ==="
    $busy = $false
    try {
        $busy = [bool](Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match 'Restart-DuneBattlegroup\.ps1' })
    } catch { }
    if ($busy) {
        Write-Log "hourly maintain is running; skip"
        return
    }
    if (-not (Test-WanUp)) {
        Write-Log "WAN down; local repairs only (no FLS/advertise)"
    }
    $exports = ""
    if ($LanIp -and $LanIp -ne "192.168.0.10") { $exports = "export DUNE_LAN_IP='$LanIp'; " }
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -d $WslDistro -u dune -- bash -lc ($exports + "exec /home/dune/.dune/bin/dune-repair-health.sh") 2>&1 | ForEach-Object {
        if ($null -eq $_) { return }
        $text = $_
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $text = $_.ToString() }
        foreach ($piece in (("$text") -split "`r")) { Write-Log $piece }
    }
    if ($LASTEXITCODE -ne 0) { Write-Log "WARNING: dune-repair-health.sh exited $LASTEXITCODE" }
    $ErrorActionPreference = $savedEap
    Write-Log "=== Dune health end ==="
} finally {
    if ($lockStream) { $lockStream.Close(); $lockStream.Dispose() }
}
