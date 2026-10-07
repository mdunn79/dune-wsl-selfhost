#Requires -RunAsAdministrator
# Register a host Task Scheduler job that keeps the battlegroup running and patched.
# Does not start a maintain run by itself. Uninstall: -Uninstall
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledMaintain.ps1"
#
# Default: Daily 6:00 AM local, repeat every hour, plus At log on for this Windows user.
# If a run is already going (a Steam depot can take ~45 minutes), a new tick is skipped.

param(
    [switch]$Uninstall,
    [string]$TaskName = "DuneBattlegroupMaintain",
    [string]$DailyAt = "06:00",
    [int]$RepeatHours = 1,
    [switch]$NoLogon
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($here)) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$script = Join-Path $here "Restart-DuneBattlegroup.ps1"
if (-not (Test-Path $script)) {
    throw "Missing $script (run this from the self-host folder)."
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task $TaskName (if it existed)."
    return
}

if ($RepeatHours -lt 1) {
    throw "RepeatHours must be at least 1"
}

try {
    $at = [datetime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "DailyAt must be 24-hour HH:mm (got '$DailyAt')"
}

$others = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
    $_.TaskName -ne $TaskName -and
    @($_.Actions) -match "Restart-DuneBattlegroup"
})
if ($others.Count -gt 0) {
    Write-Host "WARNING: another task already runs Restart-DuneBattlegroup.ps1:"
    foreach ($t in $others) {
        Write-Host ("  {0}" -f $t.TaskName)
    }
    Write-Host "Disable or delete the duplicate so hourly ticks do not overlap."
}

$ps = (Get-Command powershell.exe).Source
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $arg -WorkingDirectory $here

$daily = New-ScheduledTaskTrigger -Daily -At $at
$rep = (New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Hours $RepeatHours) -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$daily.Repetition = $rep

$triggers = @($daily)
if (-not $NoLogon) {
    $triggers += New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Scheduled task $TaskName installed."
Write-Host ("  Daily {0} local, then every {1} hour(s); At log on for {2}." -f $at.ToString("HH:mm"), $RepeatHours, $env:USERNAME)
Write-Host "  Start in: $here"
Write-Host "  If a run is already in progress, the next tick is skipped (IgnoreNew)."
Write-Host "  Log: $(Join-Path $here 'restart-dune-battlegroup.log')"
Write-Host "Uninstall: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Uninstall"
Write-Host "This did not start a maintain run. Right-click the task -> Run, or wait for the next trigger."
Write-Host "Join-port health (every 5 min, no depot/advertise): Install-DuneScheduledHealth.ps1"
