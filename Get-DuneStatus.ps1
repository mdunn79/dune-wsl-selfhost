# Joinable = Overmap AND Survival_1 both Running / true.
# Read-only. Run from this folder (does not need Administrator).
$ErrorActionPreference = "Stop"
$distro = "Ubuntu"
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $distro = [string]$cfg.Distro }
}

$wslConfig = Join-Path $env:USERPROFILE ".wslconfig"
if (-not (Test-Path $wslConfig)) {
    Write-Host "WARNING: $wslConfig is missing. Rubberbanding is likely until the installer writes autoMemoryReclaim=disabled."
} else {
    $reclaim = Get-Content -Raw $wslConfig
    if ($reclaim -notmatch "(?im)^\s*autoMemoryReclaim\s*=\s*disabled\s*$") {
        Write-Host "WARNING: autoMemoryReclaim is not disabled in .wslconfig. Windows can reclaim Hagga RAM and every client hitch/rubberbands."
        Write-Host "Re-run Restart-DuneBattlegroup.ps1 or the installer. That is a one-time wsl --shutdown only if the file still needs the change."
    } else {
        Write-Host "WSL autoMemoryReclaim=disabled (Windows will not yank Hagga pages)."
    }
}

Write-Host "Asking WSL distro $distro (user dune) for battlegroup status..."
$savedEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& wsl.exe -d $distro -u dune -- bash -lc "/home/dune/.dune/bin/battlegroup status"
$code = $LASTEXITCODE
$ErrorActionPreference = $savedEap
if ($code -ne 0) {
    throw "Could not read battlegroup status from distro $distro. If wsl.exe says E_UNEXPECTED while Ubuntu is Running, run Restart-DuneBattlegroup.ps1 (it un-wedges exec; maps bounce only if shutdown is required)."
}
Write-Host ""
Write-Host "Join from another computer only when Overmap and Survival_1 are both Running / true and Gateway is Ready (not Modifying)."
Write-Host "Queue + offline usually means Survival is still starting, or director TCP 31519 is not bound."
Write-Host "Internet timeouts with a visible listing usually mean Unreal still has no -ExternalAddress (LAN bind only)."
Write-Host "Checking advertise vs bind and LAN join listeners..."
& wsl.exe -d $distro -u dune -- bash -lc "/home/dune/.dune/bin/dune-set-advertise-ip.sh --status; echo; sudo ss -ltn | grep -E ':31982|:31519|:18888|:18889' || true; sudo ss -lun | grep -E ':7777|:7778|:7888|:7889' || true"
$lan = ""
$cfgPath2 = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath2) {
    $cfg2 = Get-Content -Raw $cfgPath2 | Invoke-Expression
    if ($cfg2.LanIp) { $lan = [string]$cfg2.LanIp.Trim() }
}
if ($lan) {
    Write-Host "LAN web admin: http://$($lan):18889  (token: wsl -u dune -- cat /home/dune/.dune/admin.token)"
}
