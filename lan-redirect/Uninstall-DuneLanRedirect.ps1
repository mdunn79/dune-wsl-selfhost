#Requires -RunAsAdministrator
# Remove the logon task and/or Windows service. Does not delete WinDivert files.

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
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
Write-Host "Removed scheduled task and service (if they existed). WinDivert files in windivert\ were left in place."
