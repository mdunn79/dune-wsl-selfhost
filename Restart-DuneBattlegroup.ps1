# Keep the Dune: Awakening WSL battlegroup running and patched to the current Steam depot.
# Queries Steam first (app_info_print 4754530). Funcom update / map roll only if the
# public buildid is newer than the installed appmanifest, or if maps are not Ready.
# Run from Windows PowerShell, not from inside Ubuntu.
# Does not wsl --shutdown and does not wipe Kubernetes operators.
#
# Daily / At log on Task Scheduler:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
# No-op days are ~1–2 minutes. A real patch can take 45 minutes.
# Watch restart-dune-battlegroup.log in this folder.

$ErrorActionPreference = "Stop"

$LogFile = Join-Path $PSScriptRoot "restart-dune-battlegroup.log"
$WslUser = "dune"
$ReadyTimeoutSec = 1200

function Write-Log([string]$Message) {
    # WSL/SteamCMD emit LF and CR; Write-Host of LF-only text staircases on Windows consoles.
    $clean = [string]$Message
    $clean = $clean -replace '\x1b\[[0-9;]*m', ''
    $clean = $clean -replace "`r", "" -replace "`n", ""
    if ([string]::IsNullOrWhiteSpace($clean)) { return }
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $clean
    Add-Content -Path $LogFile -Value $line
    [Console]::WriteLine($line)
}

function Invoke-DuneMaintain {
    $cmd = "export READY_TIMEOUT_SEC=$ReadyTimeoutSec; exec /home/dune/.dune/bin/dune-maintain.sh"
    # WSL stderr (Funcom ln, kubectl) must not become terminating ErrorRecords.
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -u $WslUser -- bash -lc $cmd 2>&1 | ForEach-Object {
        if ($null -eq $_) { return }
        $text = $_
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $text = $_.ToString()
        }
        foreach ($piece in (("$text") -split "`r")) {
            Write-Log $piece
        }
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedEap
    if ($code -ne 0) {
        throw "dune-maintain.sh failed ($code)"
    }
}

Write-Log "=== Dune battlegroup maintain begin (running + patched if needed) ==="

Write-Log "Making sure WSL is up..."
& wsl.exe -u $WslUser -- true
if ($LASTEXITCODE -ne 0) {
    throw "WSL did not start for user $WslUser"
}

Write-Log "Query Steam for app 4754530. Roll maps only if a newer depot is waiting or the world is down."
Invoke-DuneMaintain

Write-Log "Join from another PC (not this Windows host)."
Write-Log "=== Dune battlegroup maintain end ==="
