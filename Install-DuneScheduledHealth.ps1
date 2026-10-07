#Requires -RunAsAdministrator
# Register a host Task Scheduler job: join/admin health every 5 minutes.
# Does not start a health run by itself. Uninstall: -Uninstall
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledHealth.ps1"
#
# Keep DuneBattlegroupMaintain (hourly Steam/depot) installed separately.

param(
    [switch]$Uninstall,
    [string]$TaskName = "DuneBattlegroupHealth",
    [int]$RepeatMinutes = 5
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$script = Join-Path $here "Repair-DuneHealth.ps1"
if (-not (Test-Path $script)) {
    throw "Missing $script (run this from the self-host folder)."
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task $TaskName (if it existed)."
    return
}

if ($RepeatMinutes -lt 1) {
    throw "RepeatMinutes must be at least 1"
}

$others = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -ne $TaskName -and
    @($_.Actions) -match "Repair-DuneHealth"
})
if ($others.Count -gt 0) {
    Write-Host "WARNING: another task already runs Repair-DuneHealth.ps1:"
    foreach ($t in $others) {
        Write-Host ("  {0}" -f $t.TaskName)
    }
    Write-Host "Disable or delete the duplicate so 5-minute ticks do not overlap."
}

$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $here

$now = Get-Date
$untilMidnight = [datetime]::Today.AddDays(1) - $now
if ($untilMidnight.TotalMinutes -lt ($RepeatMinutes * 2)) {
    $untilMidnight = New-TimeSpan -Hours 24
}
$once = New-ScheduledTaskTrigger -Once -At $now -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes) -RepetitionDuration $untilMidnight
$daily = New-ScheduledTaskTrigger -Daily -At 00:00
$rep = (New-ScheduledTaskTrigger -Once -At ([datetime]::Today) -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes) -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$daily.Repetition = $rep

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($once, $daily) -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Scheduled task $TaskName installed."
Write-Host ("  Every {0} minute(s). Start in: {1}" -f $RepeatMinutes, $here)
Write-Host "  If a run is already in progress, the next tick is skipped (IgnoreNew)."
Write-Host "  Skips while DuneBattlegroupMaintain / Restart-DuneBattlegroup.ps1 is running."
Write-Host "  Log: $(Join-Path $here 'repair-dune-health.log')"
Write-Host "Uninstall: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Uninstall"
Write-Host "This did not start a health run. Right-click the task -> Run, or wait for the next trigger."
