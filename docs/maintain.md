# Keep it running

From PowerShell in the pack folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It always **looks**: Steam public buildid for app `4754530`, map Ready, join TCP `31982` / `31519`, advertise IPv4. It only **acts** when something is wrong or newer:

- Steam depot download + map roll only if the public buildid differs from the installed appmanifest, or there is no local manifest.
- `battlegroup start` only if Survival/Overmap pods are not Running. Joinable is Funcom Running / true, not kubectl 1/1.
- Advertise/listing patch (and a map roll) only if the public IPv4 actually changed.
- Join/director bind only if those ports are missing. FLS DNS does **not** stop Survival/Overmap on a no-op hour. `dune-fls-dns.service` rewrites Unreal sandbox DNS when Funcom recreates pods; the one-shot container restart still runs only after a depot apply, map start, or advertise change.
- Helper files are recopied only when they differ; the LAN admin is restarted only when those files changed (or the service was down).
- `wsl --shutdown` only if `.wslconfig` needed `autoMemoryReclaim=disabled`, or `wsl.exe` is wedged.

A no-op hour is about 1–2 minutes. A real patch can take around 45 minutes. After a patch it waits until Gateway is Healthy and both maps stay Running / true, then binds join ports. Output: `restart-dune-battlegroup.log`.

It also restores flannel/`spec.stop` if a Windows reboot left the world Stopped.

## Hourly + at log on

Elevated PowerShell in the pack folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledMaintain.ps1"
```

Registers **DuneBattlegroupMaintain**: Daily **6:00 AM** local, repeat **every hour**, plus **At log on** for the Windows user who ran it. **Start in** is this folder. If a run is already going, the next tick is skipped. After a host reboot, At log on brings k3s, Hagga, and join ports back without downloading the depot again.

Uninstall: `.\Install-DuneScheduledMaintain.ps1 -Uninstall`. If a hand-made task already runs `Restart-DuneBattlegroup.ps1` (any name, any folder), this installer removes it and registers **DuneBattlegroupMaintain** pointed at this folder.

## 5-minute join/admin health

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledHealth.ps1"
```

Rebinds LAN TCP `31982` / `31519` if a `kubectl port-forward` died, and starts `dune-admin.service` / `dune-fls-dns.service` if either is down. If the FLS DNS unit file was never installed, it runs `--install`. File Browser `18888` is a warning only if it is missing. If Survival and Overmap **pods are missing** (or k3s has no world namespace), it runs `dune-ensure-runtime.sh`. It does **not** query Steam, apply a depot, refresh advertise IP, or restart Unreal for FLS DNS. Pods present but not Ready is a log line only. If home WAN is down, it still does local binds and runtime restore, and it will not touch Funcom listing. It skips the tick while hourly maintain is running. Log: `repair-dune-health.log`.

Uninstall: `.\Install-DuneScheduledHealth.ps1 -Uninstall`. After an ISP outage, leave advertise/IP refresh to the next hourly maintain (a 5-minute advertise patch would roll maps).

## Read-only checks

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneStatus.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneNetHealth.ps1"
```

Joinable without rolling maps: `Get-DuneStatus.ps1`. House-PC hairpin: `Get-DuneNetHealth.ps1` ([house-pc.md](house-pc.md)).
