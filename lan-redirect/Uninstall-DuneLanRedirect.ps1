#Requires -RunAsAdministrator
# Remove the logon task and/or Windows service, and unload WinDivert so this
# folder can be deleted.

$ErrorActionPreference = "Continue"
$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$taskName = "DuneLanRedirect"
$svcId = "DuneLanRedirect"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$exe = Join-Path $here "$svcId.exe"
if (Test-Path $exe) {
    & $exe stop 2>$null | Out-Null
    & $exe uninstall 2>$null | Out-Null
}
if (Get-Service -Name $svcId -ErrorAction SilentlyContinue) {
    Stop-Service -Name $svcId -Force -ErrorAction SilentlyContinue
    sc.exe delete $svcId | Out-Null
}

foreach ($name in @("WinDivert", "WinDivert64")) {
    sc.exe stop $name 1>$null 2>$null
    sc.exe delete $name 1>$null 2>$null
}

Write-Host "Removed scheduled task, DuneLanRedirect service (if they existed), and the WinDivert driver."
Write-Host "Close any Start-DuneLanRedirect window, then this folder can be deleted."
