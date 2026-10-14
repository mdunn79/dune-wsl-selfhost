# Stop Funcom maps before Windows kills WSL (Update restart / shutdown).
# Does not wsl --shutdown. After boot, At log on maintain brings the world back.
# Register: Install-DuneScheduledMaintain.ps1 (task DuneBattlegroupPreShutdown).
# Log: stop-dune-battlegroup.log

$ErrorActionPreference = "Stop"
$LogFile = Join-Path $PSScriptRoot "stop-dune-battlegroup.log"
$WslUser = "dune"
$WslDistro = "Ubuntu"
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $WslDistro = [string]$cfg.Distro }
}

function Write-Log([string]$Message) {
    $clean = ([string]$Message) -replace '\x1b\[[0-9;]*m', '' -replace "`r", "" -replace "`n", ""
    if ([string]::IsNullOrWhiteSpace($clean)) { return }
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $clean
    Add-Content -Path $LogFile -Value $line
    [Console]::WriteLine($line)
}

Write-Log "=== Dune battlegroup pre-shutdown begin ==="
$savedEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& wsl.exe -d $WslDistro -u $WslUser -- bash -lc "exec /home/dune/.dune/bin/battlegroup stop" 2>&1 | ForEach-Object {
    if ($null -eq $_) { return }
    $text = $_
    if ($_ -is [System.Management.Automation.ErrorRecord]) { $text = $_.ToString() }
    foreach ($piece in (("$text") -split "`r")) { Write-Log $piece }
}
$code = $LASTEXITCODE
& wsl.exe -d $WslDistro -u root -- sync 2>$null | Out-Null
$ErrorActionPreference = $savedEap
if ($code -ne 0) {
    Write-Log "WARNING: battlegroup stop exited $code (Windows may already be tearing WSL down)"
} else {
    Write-Log "battlegroup stop ok"
}
Write-Log "=== Dune battlegroup pre-shutdown end ==="
