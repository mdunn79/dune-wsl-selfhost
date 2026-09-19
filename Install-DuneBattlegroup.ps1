# From-scratch Dune: Awakening self-host on Windows 11 Home via WSL2 (not Funcom Hyper-V).
# Run elevated:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneBattlegroup.ps1"
#
# Copy dune-install.config.example.ps1 to dune-install.config.ps1.
# World name, region, LAN IP, and playstyle are read from that file (not prompted).
# FlsToken is prompted only if left blank. The token is never printed.
#
# Does not wsl --shutdown unless systemd or .wslconfig actually changed.

$ErrorActionPreference = "Stop"
$SetupRoot = $PSScriptRoot
$LogFile = Join-Path $SetupRoot "install-dune-battlegroup.log"
$WslCreatorId = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"

function Write-Log([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line
    [Console]::WriteLine($line)
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RegionIndex([string]$Region) {
    $map = @{
        "Asia"           = "1"
        "Europe"         = "2"
        "North America"  = "3"
        "Oceania"        = "4"
        "South America"  = "5"
    }
    $hit = $map.Keys | Where-Object { $_.ToLowerInvariant() -eq $Region.Trim().ToLowerInvariant() } | Select-Object -First 1
    if ($hit) { return $map[$hit] }
    throw "Region must be one of: $($map.Keys -join ', ')"
}

function Show-WindowsFirewallAdvice {
    $on = @()
    foreach ($p in Get-NetFirewallProfile) {
        if ($p.Enabled) { $on += $p.Name }
    }
    if ($on.Count -eq 0) {
        Write-Log "Windows Firewall profiles are off. No Windows Firewall change is required from you."
        return
    }
    Write-Log "Windows Firewall is ON for: $($on -join ', '). This installer will not change it."
    Write-Log "If clients cannot join, allow inbound on the host (you do this, not the script):"
    Write-Log "  UDP 7777-7810 and 7888-7941 (game / IGW)"
    Write-Log "  TCP 31982 (join), 31519 (Director), 18888 (File Browser, keep off the internet)"
    Write-Log "For internet players: port-forward those UDP ranges and TCP 31982 (and 31519) to LanIp. Set AdvertiseIp to the public WAN IPv4."
    Write-Log "WSL has a separate Hyper-V firewall; this installer does configure that one."
}

function Resolve-PlayStyle($Cfg) {
    $style = "$($Cfg.PlayStyle)".Trim()
    if ([string]::IsNullOrWhiteSpace($style)) { $style = "CasualPve" }
    $ok = @{ "casualpve" = "CasualPve"; "official" = "Official" }
    $key = $style.ToLowerInvariant()
    if (-not $ok.ContainsKey($key)) {
        throw "PlayStyle must be CasualPve or Official (got '$style')"
    }
    return $ok[$key]
}

function Resolve-AdvertiseIp($Cfg) {
    $adv = "$($Cfg.AdvertiseIp)".Trim()
    if ([string]::IsNullOrWhiteSpace($adv)) { return [string]$Cfg.LanIp }
    if ($adv -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        throw "AdvertiseIp must be an IPv4 address (the host's public WAN IP), or leave it empty for LAN-only."
    }
    if ($adv -match '^(127\.|0\.0\.0\.0$)') {
        throw "AdvertiseIp cannot be $adv"
    }
    return $adv
}

function Assert-LanIp([string]$LanIp) {
    if ($LanIp -match '^(127\.|0\.0\.0\.0$|::1$)') {
        throw "LanIp $LanIp is not a LAN address. Use the host's Ethernet/Wi-Fi IPv4 from ipconfig."
    }
    $mine = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -and $_.IPAddress -notlike "127.*" } |
        Select-Object -ExpandProperty IPAddress)
    if ($mine.Count -gt 0 -and $mine -notcontains $LanIp) {
        throw "LanIp $LanIp is not assigned to the host. Addresses found: $($mine -join ', '). Put the Ethernet/Wi-Fi IPv4 in dune-install.config.ps1."
    }
}

function Get-InstallConfig {
    $path = Join-Path $SetupRoot "dune-install.config.ps1"
    $example = Join-Path $SetupRoot "dune-install.config.example.ps1"
    if (-not (Test-Path $path)) {
        Copy-Item $example $path
        throw "Created $path — set WorldName, Region, LanIp, PlayStyle, and FlsToken, then re-run."
    }
    return (Get-Content -Raw $path | Invoke-Expression)
}

function Test-WslUsable {
    $st = Get-WindowsOptionalFeature -Online -FeatureName "Microsoft-Windows-Subsystem-Linux" -ErrorAction SilentlyContinue
    return [bool]($st -and $st.State -eq "Enabled")
}

function Ensure-WslFeature {
    if (Test-WslUsable) {
        Write-Log "WSL is already installed; skipping Windows feature enable"
        return $false
    }
    $needRestart = $false
    $enabledAny = $false
    foreach ($name in @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")) {
        $st = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction SilentlyContinue
        if (-not $st) { continue }
        if ($st.State -eq "Enabled") {
            Write-Log "Windows feature $name already enabled; skipping"
            continue
        }
        Write-Log "Enabling Windows feature $name"
        $enabledAny = $true
        $r = Enable-WindowsOptionalFeature -Online -FeatureName $name -All -NoRestart
        if ($r.RestartNeeded) { $needRestart = $true }
    }
    if (-not $enabledAny) {
        Write-Log "WSL Windows features already enabled; skipping"
    }
    return $needRestart
}

function Get-WslDistro([string]$Preferred) {
    # wsl -l defaults to UTF-16; --utf8 avoids a false "no Ubuntu" miss.
    $names = @(& wsl.exe -l -q --utf8 2>$null)
    if (-not $names) { return $null }
    $trim = $names | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ }
    if ($trim | Where-Object { $_ -eq $Preferred }) { return $Preferred }
    $ubuntu = $trim | Where-Object { $_ -like "Ubuntu*" } | Select-Object -First 1
    return $ubuntu
}

function Set-WslConfig($Cfg) {
    $path = Join-Path $env:USERPROFILE ".wslconfig"
    $desired = @"
[wsl2]
memory=$($Cfg.WslMemory)
processors=$($Cfg.WslProcessors)
swap=$($Cfg.WslSwap)
networkingMode=mirrored
dnsTunneling=true
firewall=true

[experimental]
hostAddressLoopback=true
"@
    if (-not (Test-Path $path)) {
        Set-Content -Path $path -Value $desired -Encoding ASCII
        Write-Log "Wrote $path (mirrored networking, $($Cfg.WslMemory))"
        return $true
    }
    $cur = Get-Content -Raw $path
    if ($cur -match "networkingMode\s*=\s*mirrored") {
        Write-Log "Keeping existing .wslconfig (mirrored already set); not rewriting WSL settings"
        return $false
    }
    Write-Log "Existing .wslconfig found; adding mirrored networking only (keeping memory/CPU settings)"
    $text = $cur.TrimEnd()
    if ($text -notmatch '\[wsl2\]') {
        $text += "`r`n[wsl2]"
    }
    foreach ($pair in @("networkingMode=mirrored", "dnsTunneling=true", "firewall=true")) {
        $key = ($pair -split "=", 2)[0]
        if ($text -notmatch "$key\s*=") {
            $text = [regex]::Replace($text, "\[wsl2\]", "[wsl2]`r`n$pair", 1)
        }
    }
    if ($text -notmatch '\[experimental\]') {
        $text += "`r`n`r`n[experimental]`r`nhostAddressLoopback=true"
    } elseif ($text -notmatch "hostAddressLoopback\s*=") {
        $text = [regex]::Replace($text, "\[experimental\]", "[experimental]`r`nhostAddressLoopback=true", 1)
    }
    Set-Content -Path $path -Value ($text.TrimEnd() + "`r`n") -Encoding ASCII
    return $true
}

function Set-WslHyperVFirewall {
    try {
        $cur = Get-NetFirewallHyperVVMSetting -Name $WslCreatorId -ErrorAction SilentlyContinue
        $alreadyAllow = $cur -and $cur.Enabled -and ("$($cur.DefaultInboundAction)" -eq "Allow")
        if ($alreadyAllow) {
            Write-Log "WSL Hyper-V firewall inbound already Allow; skipping VM setting"
        } else {
            Write-Log "Allowing inbound on the WSL Hyper-V firewall (Home still uses this for WSL2)"
            Set-NetFirewallHyperVVMSetting -Name $WslCreatorId -Enabled True -DefaultInboundAction Allow
        }
        $rules = @(
            @{ Name = "Dune-WSL-UDP-Game"; DisplayName = "Dune WSL UDP game"; Protocol = "UDP"; Ports = "7777-7810,7888-7941" },
            @{ Name = "Dune-WSL-TCP-RMQ"; DisplayName = "Dune WSL TCP RMQ"; Protocol = "TCP"; Ports = "31982" },
            @{ Name = "Dune-WSL-TCP-Admin"; DisplayName = "Dune WSL TCP admin"; Protocol = "TCP"; Ports = "18888,31519,11717" }
        )
        $created = 0
        $skipped = 0
        foreach ($r in $rules) {
            if (Get-NetFirewallHyperVRule -Name $r.Name -ErrorAction SilentlyContinue) {
                $skipped++
                continue
            }
            New-NetFirewallHyperVRule -Name $r.Name -DisplayName $r.DisplayName -Direction Inbound -Action Allow `
                -Protocol $r.Protocol -LocalPorts $r.Ports -VMCreatorId $WslCreatorId | Out-Null
            $created++
        }
        Write-Log "WSL Hyper-V firewall rules: $created created, $skipped already present"
    } catch {
        Write-Log "WARNING: could not configure the WSL Hyper-V firewall ($($_.Exception.Message)). LAN join may fail until this works. Re-run the installer after WSL is up."
    }
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

if (-not (Test-Admin)) {
    throw "Run this script from an elevated PowerShell window."
}

$cfg = Get-InstallConfig
if ([string]::IsNullOrWhiteSpace($cfg.WorldName)) { throw "WorldName is required in dune-install.config.ps1" }
if ([string]::IsNullOrWhiteSpace($cfg.LanIp)) { throw "LanIp is required in dune-install.config.ps1" }
$regionName = $cfg.Region
if ([string]::IsNullOrWhiteSpace($regionName) -and $cfg.RegionIndex) {
    $regionName = @{ "1"="Asia"; "2"="Europe"; "3"="North America"; "4"="Oceania"; "5"="South America" }[$cfg.RegionIndex.ToString()]
}
$regionIndex = Get-RegionIndex $regionName
$playStyle = Resolve-PlayStyle $cfg
Assert-LanIp $cfg.LanIp
$advertiseIp = Resolve-AdvertiseIp $cfg

Write-Log "World '$($cfg.WorldName)' region '$regionName' bind $($cfg.LanIp) advertise $advertiseIp playstyle $playStyle"
$restartNeeded = Ensure-WslFeature
if ($restartNeeded) {
    Write-Log "Windows asked for a restart to finish WSL features. Reboot, then run this script again. Not required on every machine."
    throw "WSL Windows features enabled; reboot and re-run."
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe not found after enabling features."
}

$distro = Get-WslDistro $cfg.Distro
if ($distro) {
    Write-Log "WSL distro $distro already present; skipping Ubuntu install"
} else {
    Write-Log "Setting WSL default version to 2"
    & wsl.exe --set-default-version 2 2>$null | Out-Null
    Write-Log "Installing Ubuntu for WSL (no Hyper-V Manager / no Pro upgrade)"
    & wsl.exe --install -d Ubuntu --no-launch
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Ubuntu install exited $LASTEXITCODE. If Windows asked for a reboot, reboot and re-run. Not opening an interactive Ubuntu window."
        throw "Ubuntu did not finish installing in this pass. Reboot if Windows asked, then re-run."
    }
    $distro = $null
    foreach ($n in 1..18) {
        Start-Sleep -Seconds 5
        $distro = Get-WslDistro "Ubuntu"
        if ($distro) { break }
        Write-Log "Waiting for Ubuntu distro to register ($n/18)"
    }
    if (-not $distro) { throw "Ubuntu distro did not appear. Reboot if Windows asked, then re-run. Check with: wsl -l -v" }
}

try {
    & wsl.exe --set-default $distro | Out-Null
    Write-Log "Default WSL distro set to $distro"
} catch {
    Write-Log "Could not set default WSL distro to $distro (daily Restart-DuneBattlegroup.ps1 may need: wsl --set-default $distro)"
}

$wslConfigChanged = Set-WslConfig $cfg
& wsl.exe -d $distro -u root -- true
if ($LASTEXITCODE -ne 0) {
    throw "WSL distro $distro failed to start."
}

$systemdOut = & wsl.exe -d $distro -u root -- bash -lc "ps -p 1 -o comm="
if ($systemdOut -match "systemd") {
    Write-Log "systemd already running in $distro; skipping /etc/wsl.conf"
} else {
    Write-Log "Enabling systemd in /etc/wsl.conf"
    & wsl.exe -d $distro -u root -- bash -lc "grep -q systemd=true /etc/wsl.conf 2>/dev/null || printf '\n[boot]\nsystemd=true\n' >> /etc/wsl.conf"
    $wslConfigChanged = $true
}

if ($wslConfigChanged) {
    Write-Log "Restarting the WSL distro only (not Windows) so .wslconfig/systemd apply"
    & wsl.exe --terminate $distro
    Start-Sleep -Seconds 2
    & wsl.exe -d $distro -u root -- true
}

Set-WslHyperVFirewall
Show-WindowsFirewallAdvice

$savedProbe = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$worldProbe = & wsl.exe -d $distro -u root -- bash -lc "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1"
$ErrorActionPreference = $savedProbe
$worldExists = -not [string]::IsNullOrWhiteSpace("$worldProbe")
if ($worldExists) {
    Write-Log "Funcom world already present ($($worldProbe.ToString().Trim())); skipping token prompt"
} elseif ([string]::IsNullOrWhiteSpace($cfg.FlsToken)) {
    $sec = Read-Host "Funcom self-host token (account.duneawakening.com)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $cfg.FlsToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}
if (-not $worldExists -and [string]::IsNullOrWhiteSpace($cfg.FlsToken)) {
    throw "FlsToken is required to create a world."
}

$tokenFile = Join-Path $SetupRoot ".fls-token"
$envFile = Join-Path $SetupRoot "install.env"
try {
    if (-not $worldExists) {
        [IO.File]::WriteAllText($tokenFile, $cfg.FlsToken.Trim())
    }
    $setupUnix = Convert-WinPathToWsl $SetupRoot
    $envBody = @(
        "SETUP_SRC=$setupUnix"
        "DUNE_WORLD_NAME='$($cfg.WorldName)'"
        "DUNE_REGION_INDEX=$regionIndex"
        "DUNE_LAN_IP=$($cfg.LanIp)"
        "DUNE_ADVERTISE_IP=$advertiseIp"
        "DUNE_PLAY_STYLE=$playStyle"
    ) -join "`n"
    [IO.File]::WriteAllText($envFile, $envBody)
    Write-Log "Installing Linux depot + k3s + world inside $distro (already-installed pieces are skipped)"
    $linux = "sed 's/\r`$//' '$setupUnix/run-linux-install.sh' | bash -s -- '$setupUnix'"
    $savedEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & wsl.exe -d $distro -u root -- bash -lc $linux 2>&1 | ForEach-Object {
        $text = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.ToString() } else { "$_" }
        foreach ($piece in ($text -split "`r")) {
            $clean = [string]$piece
            if ($clean -match 'eyJ') { $clean = "<redacted jwt>" }
            $clean = $clean -replace '\x1b\[[0-9;]*m', '' -replace "`n", ""
            if (-not [string]::IsNullOrWhiteSpace($clean)) { Write-Log $clean }
        }
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedEap
    if ($code -ne 0) {
        throw "Linux install failed ($code). See $LogFile"
    }
}
finally {
    if (Test-Path $tokenFile) { Remove-Item -Force $tokenFile -ErrorAction SilentlyContinue }
    if (Test-Path $envFile) { Remove-Item -Force $envFile -ErrorAction SilentlyContinue }
}

Write-Log "Join as $($cfg.WorldName) at $advertiseIp (bound on $($cfg.LanIp)). Do not join from the host."
Write-Log "Daily maintain: Restart-DuneBattlegroup.ps1 (queries Steam; rolls maps only if a newer depot is waiting)."
Write-Log "=== Install-DuneBattlegroup end ==="
