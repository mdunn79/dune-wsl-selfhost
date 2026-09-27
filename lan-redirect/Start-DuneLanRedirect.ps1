#Requires -RunAsAdministrator
# Gaming PC only. Rewrites Funcom public listing IP to the Dune host LAN bind.
#
# Manual:     .\Start-DuneLanRedirect.ps1
# Hibernate:  .\Start-DuneLanRedirect.ps1 -WatchDune
# Debug:      .\Start-DuneLanRedirect.ps1 -VerbosePackets
# Install:    .\Install-DuneLanRedirect.ps1
#             .\Install-DuneLanRedirect.ps1 -Service

param(
    [string]$LanIp = "",
    [string]$PublicIp = "",
    [switch]$Quiet,
    [switch]$VerbosePackets,
    [switch]$WatchDune,
    [switch]$AllowHost,
    [string]$WinDivertVersion = "2.2.2-A"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cs = Join-Path $here "DuneLanRedirect.cs"
$wdDir = Join-Path $here "windivert"
$cfgPath = Join-Path $here "dune-client.config.ps1"
$logDir = Join-Path $env:LOCALAPPDATA "DuneLanRedirect"
$logFile = Join-Path $logDir "redirect.log"
$duneNames = @(
    "DuneSandbox-Win64-Shipping",
    "DuneAwakening",
    "DuneSandbox"
)

function Test-Ipv4([string]$Ip) {
    return $Ip -match '^\d{1,3}(\.\d{1,3}){3}$'
}

function Write-RedirectLog([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $logFile -Value $line
    if (-not $Quiet) { [Console]::WriteLine($line) }
}

function Get-PublicIpv4 {
    $urls = @("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")
    foreach ($u in $urls) {
        try {
            $ip = ([string](Invoke-RestMethod -Uri $u -TimeoutSec 8)).Trim()
            if (Test-Ipv4 $ip) { return $ip }
        } catch {}
    }
    throw "Could not look up the public IPv4. Set PublicIp in dune-client.config.ps1."
}

function Install-WinDivert {
    $dll = Join-Path $wdDir "WinDivert.dll"
    $sys = Join-Path $wdDir "WinDivert64.sys"
    if ((Test-Path $dll) -and (Test-Path $sys)) { return }
    New-Item -ItemType Directory -Force -Path $wdDir | Out-Null
    $zip = Join-Path $here "WinDivert-$WinDivertVersion.zip"
    $url = "https://github.com/basil00/WinDivert/releases/download/v2.2.2/WinDivert-$WinDivertVersion.zip"
    Write-RedirectLog "Downloading WinDivert"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    $extract = Join-Path $here "windivert-extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    $x64 = Get-ChildItem -Path $extract -Recurse -Filter "WinDivert.dll" | Where-Object { $_.DirectoryName -match '\\x64$' } | Select-Object -First 1
    if (-not $x64) { throw "WinDivert zip had no x64\WinDivert.dll" }
    Copy-Item (Join-Path $x64.DirectoryName "WinDivert.dll") $dll -Force
    Copy-Item (Join-Path $x64.DirectoryName "WinDivert64.sys") $sys -Force
    Remove-Item -Force $zip
    Remove-Item -Recurse -Force $extract
    Write-RedirectLog "WinDivert x64 installed (LGPL, basil00/WinDivert)"
}

if (-not (Test-Path $cs)) { throw "Missing $cs" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path $cfgPath) {
    $cfg = Get-Content -Raw $cfgPath | Invoke-Expression
    if ([string]::IsNullOrWhiteSpace($LanIp) -and $cfg.LanIp) { $LanIp = [string]$cfg.LanIp }
    if ([string]::IsNullOrWhiteSpace($PublicIp) -and $cfg.PublicIp) { $PublicIp = [string]$cfg.PublicIp }
    if ($cfg.DuneProcessNames) { $duneNames = @($cfg.DuneProcessNames) }
}

if ([string]::IsNullOrWhiteSpace($LanIp)) {
    throw "Set LanIp in dune-client.config.ps1 (copy the example) or pass -LanIp. Use the Dune host Ethernet/Wi-Fi IPv4."
}
$LanIp = $LanIp.Trim()
if (-not (Test-Ipv4 $LanIp)) { throw "LanIp must be dotted IPv4" }
if ($LanIp -match '^(127\.|0\.)') { throw "LanIp must be the host LAN address, not loopback" }

if (-not $AllowHost) {
    $mine = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress)
    if ($mine -contains $LanIp) {
        throw "LanIp $LanIp is this PC. Run the redirector on the gaming PC, not on the Dune host. (Override: -AllowHost)"
    }
}

if ([string]::IsNullOrWhiteSpace($PublicIp) -or $PublicIp.Trim() -match '^(auto|public)$') {
    $PublicIp = Get-PublicIpv4
}
$PublicIp = $PublicIp.Trim()
if (-not (Test-Ipv4 $PublicIp)) { throw "PublicIp must be dotted IPv4 or auto" }
if ($PublicIp -eq $LanIp) { throw "PublicIp and LanIp are the same" }

if ([Environment]::Is64BitProcess -eq $false) {
    throw "Use 64-bit PowerShell. 32-bit cannot load WinDivert64."
}

Install-WinDivert

$verboseN = 0
if ($VerbosePackets) { $verboseN = 1 }

if (-not ([System.Management.Automation.PSTypeName]"DuneLanRedirect").Type) {
    $src = [IO.File]::ReadAllText($cs)
    Add-Type -TypeDefinition $src -Language CSharp
}

Write-RedirectLog "start public=$PublicIp lan=$LanIp quiet=$Quiet verbose=$verboseN watch=$WatchDune"
[DuneLanRedirect]::Running = $true
$transcribed = $false
if ($Quiet) {
    Start-Transcript -Path $logFile -Append | Out-Null
    $transcribed = $true
}

function Test-DuneClientRunning {
    foreach ($n in $duneNames) {
        if (Get-Process -Name $n -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

function Invoke-RedirectOnce {
    [DuneLanRedirect]::Running = $true
    return [DuneLanRedirect]::Run($wdDir, $PublicIp, $LanIp, $verboseN, $true)
}

try {
    if (-not $WatchDune) {
        $code = Invoke-RedirectOnce
        Write-RedirectLog "exit $code"
        exit $code
    }

    Write-RedirectLog ("watch Dune processes: " + ($duneNames -join ", "))
    if (-not $Quiet) {
        Write-Host "Hibernating until Dune starts. Redirect arms only while the client is running. Ctrl+C to quit."
    }
    $script:keepWatch = $true
    [Console]::TreatControlCAsInput = $false

    $worker = $null
    $armed = $false
    try {
        while ($true) {
            $running = Test-DuneClientRunning
            if ($armed -and $script:workerAsync -and $script:workerAsync.IsCompleted) {
                try { $worker.EndInvoke($script:workerAsync) | Out-Null } catch {}
                $worker.Dispose()
                $worker = $null
                $armed = $false
                Write-RedirectLog "redirect worker exited"
            }
            if ($running -and -not $armed) {
                Write-RedirectLog "Dune detected; arming redirect"
                [DuneLanRedirect]::Running = $true
                $worker = [PowerShell]::Create()
                $null = $worker.AddScript({
                    param($dir, $pub, $lan, $v)
                    [DuneLanRedirect]::Run($dir, $pub, $lan, $v, $false)
                }).AddArgument($wdDir).AddArgument($PublicIp).AddArgument($LanIp).AddArgument($verboseN)
                $script:workerAsync = $worker.BeginInvoke()
                $armed = $true
            } elseif ((-not $running) -and $armed) {
                Write-RedirectLog "Dune exited; hibernating redirect"
                [DuneLanRedirect]::RequestStop()
                if ($worker -and $script:workerAsync) {
                    try { $worker.EndInvoke($script:workerAsync) | Out-Null } catch {}
                    $worker.Dispose()
                }
                $worker = $null
                $armed = $false
            }
            Start-Sleep -Seconds 3
        }
    } finally {
        [DuneLanRedirect]::RequestStop()
        if ($worker -and $script:workerAsync) {
            try { $worker.EndInvoke($script:workerAsync) | Out-Null } catch {}
            $worker.Dispose()
        }
        Write-RedirectLog "watch stopped"
    }
} finally {
    if ($transcribed) { Stop-Transcript | Out-Null }
}
