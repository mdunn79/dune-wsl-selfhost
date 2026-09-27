# Read-only Hagga net health. Run on the HOST, not the gaming PC.
# Rubberband signal = ServerMove TimeStamp expired in Survival logs.
# Join path = RemoteAddr (public IP = hairpin, 192.168.x = LAN/redirect).
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Get-DuneNetHealth.ps1
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Get-DuneNetHealth.ps1 -WatchSeconds 60

param(
    [int]$WatchSeconds = 0
)

$ErrorActionPreference = "Stop"
$distro = "Ubuntu"
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $distro = [string]$cfg.Distro }
}

$sh = Join-Path $PSScriptRoot "Get-DuneNetHealth.sh"
if (-not (Test-Path $sh)) { throw "Missing $sh" }

$watch = 0
if ($WatchSeconds -gt 0) { $watch = $WatchSeconds }

$setupUnix = (Resolve-Path $PSScriptRoot).Path
if ($setupUnix -notmatch '^([A-Za-z]):\\(.*)$') { throw "Cannot map suite path into WSL" }
$unix = "/mnt/$($Matches[1].ToLowerInvariant())/$($Matches[2] -replace '\\','/')"

Write-Host "Hagga net health from distro $distro (read-only). Watch=${watch}s"
$savedEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& wsl.exe -d $distro -u dune -- bash -lc "sed 's/\r`$//' '$unix/Get-DuneNetHealth.sh' | SINCE=15m WATCH=$watch bash"
$code = $LASTEXITCODE
$ErrorActionPreference = $savedEap
if ($code -ne 0) {
    throw "Get-DuneNetHealth failed ($code). If wsl.exe is E_UNEXPECTED, run Restart-DuneBattlegroup.ps1."
}
Write-Host ""
Write-Host "If the LAN redirect POC works, RemoteAddr for the house PC should be 192.168.x (lan), not the public WAN IP (hairpin-or-self-wan)."
Write-Host "timestamp_expired_count near 0 while someone is moving is the rubberband-stopped signal."
