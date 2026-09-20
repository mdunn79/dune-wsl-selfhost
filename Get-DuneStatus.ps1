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
Write-Host "Join from another computer only when Overmap and Survival_1 are both Running / true."
Write-Host "A spinner in the server tab usually means Survival is still starting (PostLandscapePhysics), not that the listing is missing."
