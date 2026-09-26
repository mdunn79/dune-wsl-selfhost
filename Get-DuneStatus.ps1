# Joinable = Overmap AND Survival_1 both Running / true.
# Run from this folder (does not need Administrator).
$ErrorActionPreference = "Stop"
$distro = "Ubuntu"
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $distro = [string]$cfg.Distro }
}

Write-Host "Asking WSL distro $distro (user dune) for battlegroup status..."
& wsl.exe -d $distro -u dune -- bash -lc "/home/dune/.dune/bin/battlegroup status"
if ($LASTEXITCODE -ne 0) {
    throw "Could not read battlegroup status from distro $distro. Is Ubuntu installed and the world created?"
}
Write-Host ""
Write-Host "Join from another computer only when Overmap and Survival_1 are both Running / true and Gateway is Ready (not Modifying)."
Write-Host "Queue + offline usually means Survival is still starting, or director TCP 31519 is not bound."
Write-Host "Internet timeouts with a visible listing usually mean Unreal still has no -ExternalAddress (LAN bind only)."
Write-Host "Checking advertise vs bind and LAN join listeners..."
& wsl.exe -d $distro -u dune -- bash -lc "/home/dune/.dune/bin/dune-set-advertise-ip.sh --status; echo; sudo ss -ltn | grep -E ':31982|:31519' || true; sudo ss -lun | grep -E ':7777|:7778|:7888|:7889' || true"
