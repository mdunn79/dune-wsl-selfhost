# Keep the Dune: Awakening WSL battlegroup running and patched to the current Steam depot.
# Queries Steam first (app_info_print 4754530). Funcom update / map roll only if the
# public buildid is newer than the installed appmanifest, or if maps are not Ready.
# Run from Windows PowerShell, not from inside Ubuntu.
# Copies helper scripts from this folder into WSL (idempotent). Does not wipe operators.
# Does not wsl --shutdown unless .wslconfig actually needed a change, or wsl.exe is wedged.
#
# Daily / At log on Task Scheduler:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
# Healthy no-op days are ~1–2 minutes (Steam query + join bind if missing). A real patch can take 45 minutes.
# Watch restart-dune-battlegroup.log in this folder.

$ErrorActionPreference = "Stop"

$LogFile = Join-Path $PSScriptRoot "restart-dune-battlegroup.log"
$WslUser = "dune"
$WslDistro = "Ubuntu"
$ReadyTimeoutSec = 1200
$LanIp = ""
$cfgPath = Join-Path $PSScriptRoot "dune-install.config.ps1"
if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ($cfg.Distro) { $WslDistro = [string]$cfg.Distro }
    if ($cfg.LanIp) { $LanIp = [string]$cfg.LanIp.Trim() }
}

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

function Convert-WinPathToWsl([string]$WinPath) {
    $full = (Resolve-Path $WinPath).Path
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot map $WinPath into /mnt"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = ($Matches[2] -replace '\\', '/')
    return "/mnt/$drive/$rest"
}

function Repair-WslReclaim {
    $path = Join-Path $env:USERPROFILE ".wslconfig"
    if (-not (Test-Path $path)) {
        Write-Log "No $path yet; installer owns the first write. Skipping reclaim repair."
        return $false
    }
    $orig = (Get-Content -Raw $path).TrimEnd()
    $text = [regex]::Replace($orig, "(?m)^\s*pageReporting\s*=.*\r?\n?", "")
    if ($text -match "(?im)^\s*autoMemoryReclaim\s*=") {
        if ($text -notmatch "(?im)^\s*autoMemoryReclaim\s*=\s*disabled\s*$") {
            $text = [regex]::Replace($text, "(?im)^\s*autoMemoryReclaim\s*=.*$", "autoMemoryReclaim=disabled")
        }
    } elseif ($text -match "\[experimental\]") {
        $text = [regex]::Replace($text, "\[experimental\]", "[experimental]`r`nautoMemoryReclaim=disabled", 1)
    } else {
        $text += "`r`n`r`n[experimental]`r`nautoMemoryReclaim=disabled"
    }
    $text = $text.TrimEnd()
    if ($text -eq $orig) { return $false }
    Set-Content -Path $path -Value ($text + "`r`n") -Encoding ASCII
    Write-Log "Updated $path to autoMemoryReclaim=disabled (stops Windows reclaiming Hagga RAM)"
    return $true
}

function Invoke-WslTrue {
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & wsl.exe -d $WslDistro -u $WslUser -- /bin/true 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedEap
    return @{ Code = $code; Text = $out }
}

function Start-WslDistro {
    $probe = Invoke-WslTrue
    if ($probe.Code -eq 0) { return }
    $blob = "$($probe.Text)"
    Write-Log "WSL exec failed ($($probe.Code)): $($blob.Trim())"
    if ($blob -match 'E_UNEXPECTED|Catastrophic') {
        Write-Log "WSL control plane wedged (exec fails while the distro may still show Running). Terminating $WslDistro once."
        & wsl.exe --terminate $WslDistro 2>$null | Out-Null
        Start-Sleep -Seconds 3
        $probe = Invoke-WslTrue
        if ($probe.Code -eq 0) { return }
        Write-Log "Terminate did not unwedge exec; wsl --shutdown once (maps will bounce if they were up)."
        & wsl.exe --shutdown
        Start-Sleep -Seconds 8
        $probe = Invoke-WslTrue
        if ($probe.Code -eq 0) { return }
    }
    throw "WSL distro $WslDistro did not start for user $WslUser"
}

function Sync-DuneHelpers {
    $setupUnix = Convert-WinPathToWsl $PSScriptRoot
    $names = @(
        "dune-maintain.sh",
        "dune-ensure-join.sh",
        "dune-ensure-runtime.sh",
        "dune-fix-fls-dns.sh",
        "dune-set-advertise-ip.sh",
        "apply-k8s-hosts.sh",
        "coredns-custom.yaml",
        "dune-admin.py",
        "dune-admin.sh",
        "dune-admin.service",
        "dune-admin-lib.py",
        "dune-admin.html"
    )
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -d $WslDistro -u root -- bash -lc "install -d -o dune -g dune -m 755 /home/dune/.dune/bin"
    foreach ($n in $names) {
        $win = Join-Path $PSScriptRoot $n
        if (-not (Test-Path $win)) { continue }
        $src = "$setupUnix/$n"
        $dest = "/home/dune/.dune/bin/$n"
        & wsl.exe -d $WslDistro -u root -- bash -lc "sed 's/\\r`$//' '$src' > '$dest' && chmod +x '$dest' && chown dune:dune '$dest'"
        if ($LASTEXITCODE -ne 0) {
            Write-Log "WARNING: could not refresh $n"
        }
    }
    $ErrorActionPreference = $savedEap
    Write-Log "helpers-synced"
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -d $WslDistro -u root -- bash -lc "/home/dune/.dune/bin/dune-admin.sh --install"
    if ($LASTEXITCODE -ne 0) {
        Write-Log "WARNING: dune-admin install/restart failed"
    } else {
        Write-Log "dune-admin listening on LAN TCP 18889"
    }
    $ErrorActionPreference = $savedEap
}

function Invoke-DuneMaintain {
    $exports = "export READY_TIMEOUT_SEC=$ReadyTimeoutSec"
    if (-not [string]::IsNullOrWhiteSpace($LanIp) -and $LanIp -ne "192.168.0.10") {
        $exports += "; export DUNE_LAN_IP='$LanIp'"
    }
    $cmd = "$exports; exec /home/dune/.dune/bin/dune-maintain.sh"
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -d $WslDistro -u $WslUser -- bash -lc $cmd 2>&1 | ForEach-Object {
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

$reclaimChanged = Repair-WslReclaim
if ($reclaimChanged) {
    Write-Log "Applying autoMemoryReclaim=disabled with wsl --shutdown (one-time; later daily runs skip this)."
    & wsl.exe --shutdown
    Start-Sleep -Seconds 8
}

Write-Log "Making sure WSL distro $WslDistro is up..."
Start-WslDistro

Write-Log "Refreshing Linux helpers from this folder (no map roll)."
Sync-DuneHelpers

Write-Log "Query Steam for app 4754530. Roll maps only if a newer depot is waiting or the world is down."
Invoke-DuneMaintain

Write-Log "Join from another computer only when Survival is Running / true (not while Gateway is Modifying)."
Write-Log "=== Dune battlegroup maintain end ==="
