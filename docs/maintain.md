# Keep it running

From PowerShell in the pack folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It always **looks**: Steam public buildid for app `4754530`, map Ready, join TCP `31982` / `31519`, advertise IPv4. It only **acts** when something is wrong or newer:

- Steam depot download + map roll only if the public buildid differs from the installed appmanifest, or there is no local manifest.
- `battlegroup start` if Survival/Overmap pods are missing or Funcom is not Running / true. Joinable is Funcom Running / true, not kubectl 1/1. After start or a depot roll, maintain waits for that Funcom Ready streak before it binds join ports and exits.
- Advertise/listing patch (and a map roll) only if the public IPv4 actually changed.
- Join/director bind only if those ports are missing. `dune-fls-dns.service` rewrites Unreal sandbox DNS and MQ/DB host IPs when Funcom recreates pods. If MQ IPs change and a map's current log already shows admin RMQ TCP failure, it restarts only that Unreal container. It does not stop Survival/Overmap on a no-op hour.
- Helpers recopy only when they differ. LAN admin restarts only if those files changed or the service was down.
- `wsl --shutdown` only if `.wslconfig` needed `autoMemoryReclaim=disabled`, or `wsl.exe` is wedged.

A no-op hour is about 1–2 minutes. A real patch can take around 45 minutes. After a patch or At-logon start it waits until both maps stay Funcom Running / true, then binds join ports. Output: `restart-dune-battlegroup.log`.

It also restores flannel/`spec.stop` if a Windows reboot left the world Stopped.

## Hourly + at log on

Elevated PowerShell in the pack folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledMaintain.ps1"
```

Registers **DuneBattlegroupMaintain**: Daily **6:00 AM** local, repeat **every hour**, plus **At log on** for the Windows user who ran it. Also **DuneBattlegroupWatch**: At log on it opens a **Dune battlegroup** window in that session (PowerShell host hidden). It polls LAN `/status.json` every 15s for joinable, online count, and map Ready (no roster names). Windows `WM_QUERYENDSESSION` waits on that window while it runs `battlegroup stop`. Leave it open (minimize is fine). Closing it does not stop Funcom; Windows then will not wait. **DuneBattlegroupPreShutdown** (event 1074) is a backup only: Windows does not wait for that task. **Start in** is this folder. If a run is already going, the next tick is skipped. After a host reboot, At log on brings k3s, Hagga, and join ports back without downloading the depot again.

Those tasks are Interactive. They run only while that Windows user is signed in. For an unattended reboot (Windows Update, power loss), enable automatic logon as **the same account** that ran this installer. Run `netplwiz`, uncheck **Users must enter a user name and password to use this computer**, and set that account. Confirm:

```powershell
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' | Select-Object AutoAdminLogon, DefaultUserName
```

Expect `AutoAdminLogon` `1` and that username. Sitting at the lock screen does not start WSL. Autologon skips the sign-in screen and stores that user’s password. If you do not want that, log in after reboot or run `Restart-DuneBattlegroup.ps1`.

Uninstall: `.\Install-DuneScheduledMaintain.ps1 -Uninstall`. If a hand-made task already runs `Restart-DuneBattlegroup.ps1` (any name, any folder), this installer removes it and registers **DuneBattlegroupMaintain** pointed at this folder.

## 5-minute join/admin health

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledHealth.ps1"
```

Rebinds LAN TCP `31982` / `31519` if a port-forward died. Starts `dune-admin.service` / `dune-fls-dns.service` if down (`--install` if the DNS unit was never copied). File Browser `18888` missing is a warning only. Missing Survival/Overmap pods (or no world namespace): `dune-ensure-runtime.sh`. It does not query Steam, apply a depot, refresh advertise IP, or restart Unreal for FLS DNS. Pods present but not Ready: log only. WAN down: local binds still run; listing is not touched. Skips the tick while hourly maintain is running. At log on it also runs one health pass (skips if maintain is running). Join bind after reboot comes from maintain. Log: `repair-dune-health.log`.

Uninstall: `.\Install-DuneScheduledHealth.ps1 -Uninstall`. After an ISP outage, leave advertise/IP refresh to the next hourly maintain (a 5-minute advertise patch would roll maps).

## Read-only checks

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneStatus.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneNetHealth.ps1"
```

Joinable without rolling maps: `Get-DuneStatus.ps1`. House-PC hairpin: `Get-DuneNetHealth.ps1` ([house-pc.md](house-pc.md)).
