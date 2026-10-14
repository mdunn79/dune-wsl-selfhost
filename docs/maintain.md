# Keep it running

From PowerShell in the pack folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It always **looks**: Steam public buildid for app `4754530`, map Ready, join TCP `31982` / `31519`, advertise IPv4. It only **acts** when something is wrong or newer:

- Steam depot download + map roll only if the public buildid differs from the installed appmanifest, or there is no local manifest.
- `battlegroup start` only if Survival/Overmap pods are not Running. Joinable is Funcom Running / true, not kubectl 1/1.
- Advertise/listing patch (and a map roll) only if the public IPv4 actually changed.
- Join/director bind only if those ports are missing. `dune-fls-dns.service` rewrites Unreal sandbox DNS and MQ/DB host IPs when Funcom recreates pods. If MQ IPs change and a map's current log already shows admin RMQ TCP failure, it restarts only that Unreal container. It does not stop Survival/Overmap on a no-op hour.
- Helpers recopy only when they differ. LAN admin restarts only if those files changed or the service was down.
- `wsl --shutdown` only if `.wslconfig` needed `autoMemoryReclaim=disabled`, or `wsl.exe` is wedged.

A no-op hour is about 1–2 minutes. A real patch can take around 45 minutes. After a patch it waits until Gateway is Healthy and both maps stay Running / true, then binds join ports. Output: `restart-dune-battlegroup.log`.

It also restores flannel/`spec.stop` if a Windows reboot left the world Stopped.

## Hourly + at log on

Elevated PowerShell in the pack folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledMaintain.ps1"
```

Registers **DuneBattlegroupMaintain**: Daily **6:00 AM** local, repeat **every hour**, plus **At log on** for the Windows user who ran it. Also **DuneBattlegroupPreShutdown**: on Windows event 1074 (restart/shutdown) it runs `battlegroup stop` so Funcom is not only killed with the WSL VM. **Start in** is this folder. If a run is already going, the next tick is skipped. After a host reboot, At log on brings k3s, Hagga, and join ports back without downloading the depot again. This host autologon (`Winlogon AutoAdminLogon=1`) is what makes At log on fire after a patch reboot.

Uninstall: `.\Install-DuneScheduledMaintain.ps1 -Uninstall`. If a hand-made task already runs `Restart-DuneBattlegroup.ps1` (any name, any folder), this installer removes it and registers **DuneBattlegroupMaintain** pointed at this folder.

## 5-minute join/admin health

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledHealth.ps1"
```

Rebinds LAN TCP `31982` / `31519` if a port-forward died. Starts `dune-admin.service` / `dune-fls-dns.service` if down (`--install` if the DNS unit was never copied). File Browser `18888` missing is a warning only. Missing Survival/Overmap pods (or no world namespace): `dune-ensure-runtime.sh`. It does not query Steam, apply a depot, refresh advertise IP, or restart Unreal for FLS DNS. Pods present but not Ready: log only. WAN down: local binds still run; listing is not touched. Skips the tick while hourly maintain is running. Also At log on, so the 5-minute clock starts after a reboot instead of waiting for the next midnight daily trigger. Log: `repair-dune-health.log`.

Uninstall: `.\Install-DuneScheduledHealth.ps1 -Uninstall`. After an ISP outage, leave advertise/IP refresh to the next hourly maintain (a 5-minute advertise patch would roll maps).

## Read-only checks

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneStatus.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneNetHealth.ps1"
```

Joinable without rolling maps: `Get-DuneStatus.ps1`. House-PC hairpin: `Get-DuneNetHealth.ps1` ([house-pc.md](house-pc.md)).
