# Dune: Awakening self-host on Windows 11 Home (WSL)

Runs Funcom’s **Linux** battlegroup inside WSL2. It does **not** use Funcom’s Hyper-V VM, Hyper-V Manager, or Windows 11 Pro.

**The host** is the Windows 11 PC where you run this installer — your machine, not anyone else’s. Players can join from the LAN or from the internet if you port-forward. Do **not** join the world from the host itself (WSL mirrored networking does not hairpin).

If the listing uses your **public** IPv4 (`AdvertiseIp = "auto"`), Funcom has no connect-by-IP. A second PC in the house is still sent to the WAN address and back in through the router. That path often rubberbands even when the world is healthy and internet friends are fine. Copy the `lan-redirect` folder to those house PCs; see [House PCs when the listing is public](#house-pcs-when-the-listing-is-public).

The scripts in this folder are MIT. The game files SteamCMD downloads are Funcom’s; this pack does not redistribute them.

## What you need

- **Windows 11 Home is enough** (22H2 or newer). You do **not** need WSL or Ubuntu already installed — the installer turns on the Windows WSL features, installs Ubuntu, and configures WSL2 (mirrored networking, systemd, WSL firewall).
- **CPU virtualization enabled in BIOS/UEFI** (Intel VT-x / AMD-V / SVM). In Windows, Task Manager → Performance → CPU should say Virtualization: Enabled. If it says Disabled, turn it on in firmware or WSL2 will not start.
- CPU with **AVX2** (Funcom’s Unreal requirement).
- **About 32 GB RAM on the host**, preferably more. Funcom’s self-host wants a large allocation. The example gives **32 GB to WSL**; that only works if the host has about 64 GB. On a 32 GB host set `WslMemory` to `24GB`. A 16 GB host is not enough.
- **~80 GB free disk** (Ubuntu + k3s + Funcom’s Linux depot).
- Internet on the host for Ubuntu, SteamCMD, and cert-manager.
- A **second computer** to play from (LAN or internet). Joining from the host is unreliable.
- A Funcom **self-host token** from [account.duneawakening.com](https://account.duneawakening.com/) (Self-Host / experimental section for your account).
- The **Dune: Awakening Experimental** client on every machine that will play (Steam; not the live/main branch). Client build must match the Linux depot this installer downloads.

You do **not** need: WSL preinstalled, Ubuntu preinstalled, Windows 11 Pro, Hyper-V Manager, Funcom’s Windows SteamCMD installer, or a Steam account for the dedicated server (SteamCMD uses anonymous login).

First install often takes **45–120 minutes** (Steam depot + first map boot). Windows itself may require **one reboot** the first time WSL features are enabled. After reboot, run the same installer command again; it continues from there.

## 1. Put this folder on the host

On GitHub: **Code → Download ZIP**. Extract it. You should see `README.md` and `Install-DuneBattlegroup.ps1` in the **same** folder (GitHub often names the extract `dune-wsl-selfhost-main`). Move that folder somewhere stable on the host, for example `C:\dune-wsl-selfhost`.

The installer must be run from **that** folder. Do not scatter the scripts. If Windows marks the ZIP as blocked, right-click the `.ps1` / `.bat` files → Properties → Unblock, or in PowerShell: `Unblock-File .\*` .

## 2. Get your Funcom token

1. Sign in at [account.duneawakening.com](https://account.duneawakening.com/).
2. Create or copy the self-host token Funcom shows for your account.
3. Keep it private. Anyone with it can manage your self-host entitlement.

You can paste it into the config file in the next step, or leave that field empty and type it when the installer asks (it will not print the token).

## 3. Create and edit your config

Copy the example, then set the world name and (if you want) the token:

```powershell
copy .\dune-install.config.example.ps1 .\dune-install.config.ps1
notepad .\dune-install.config.ps1
```

If you run the installer with no `dune-install.config.ps1`, it copies the example for you and **stops**, so you can edit it and run again.

Fill in at least these:

| Field | What to put |
| --- | --- |
| `WorldName` | The name players see in the self-host list. No `'` or `\|`. Example: `"My Sietch"`. |
| `Region` | Exactly one of: `Asia`, `Europe`, `North America`, `Oceania`, `South America`. This is Funcom’s region menu, not Windows locale. |
| `LanIp` | Leave `""` unless auto-detect is wrong. The installer picks Ethernet, then Wi-Fi. Not `127.0.0.1`. |
| `AdvertiseIp` | Leave `""` for LAN-only (typical). Funcom does **not** need a static ISP address. Internet: `"auto"` looks up the **current** public IPv4 at install time. House PCs on that public listing need `lan-redirect` ([below](#house-pcs-when-the-listing-is-public)). |
| `PlayStyle` | `CasualPve` or `Official`. See [Play styles](#play-styles). |
| `FlsToken` | Your Funcom token in quotes, or `""` to be prompted. |

Optional, but worth checking:

| Field | What it does |
| --- | --- |
| `Distro` | WSL distro name. Leave `Ubuntu` unless the host already has a different Ubuntu name. |
| `WslMemory` | RAM given to WSL. Stay **below** the host’s physical RAM. |
| `WslProcessors` | CPU cores given to WSL. Do not exceed the host’s core count. |
| `WslSwap` | WSL swap size. |

**Finding `LanIp` if you must set it:** on the host, in PowerShell, run `ipconfig`. Use the IPv4 of Ethernet or Wi-Fi (often `192.168.x.x` or `10.x.x.x`). Skip `127.0.0.1` and VPN/virtual adapters. The installer refuses an address that is not assigned to the host.

**Finding `AdvertiseIp`:** LAN-only — leave it empty. Funcom then lists `LanIp`, and house PCs join that address directly. Internet is optional: set `AdvertiseIp = "auto"` so the installer looks up the current public IPv4 (a “what is my IP” result, not a static assignment). That address is written in **two** places: Funcom’s directory (`HOST_DATACENTER_IP_ADDRESS`) and Unreal `-ExternalAddress`. The game still **binds** `LanIp`. Funcom’s directory stores a literal IPv4; it does not take a hostname or DDNS name. There is also no LAN/WAN split: every client, including a PC in the same house, is told that one address. If the ISP later changes the address, set `"auto"` again and re-run, or let `Restart-DuneBattlegroup.ps1` refresh it. `LanIp` stays the private address the router forwards **to**.

Do **not** set k3s `node-external-ip` to the WAN address on WSL. Funcom’s Alpine VM can; WSL’s k3s agent then dials `WAN:6443` and the cluster wedges. This installer never does that.

Do not upload or share `dune-install.config.ps1`. It can hold the Funcom token. The example file in this repo is only a template.

## 4. Run the installer (elevated)

1. Right-click **`Install.bat`** → **Run as administrator**. (Double-click also works; it will prompt for elevation.) A normal non-admin window will fail.
2. Leave the window open. The first run can take a long time.

The script, in order: enables Windows WSL features **if they are not already on**, installs Ubuntu **if the host has none**, writes or repairs `.wslconfig` only when a required key is missing or wrong (`networkingMode=mirrored`, `autoMemoryReclaim=disabled`; a VM restart happens only then), turns on systemd if needed, opens the WSL Hyper-V firewall if needed, downloads Funcom’s Linux depot with SteamCMD if it is not already there, starts k3s, creates the world, then waits until Overmap **and** Survival stay Ready (up to about 20 minutes on that last wait). Survival often SIGSEGVs once on first boot and comes back; the installer waits through that.

Re-running is safe on a world that is already up. Already-installed WSL, Ubuntu, packages, SteamCMD, the depot, k3s, operators, and an existing world are skipped. Helper scripts in `/home/dune/.dune/bin` are refreshed from this folder. It will not wipe operators or recreate the world. If maps are already Ready and the advertise IP did not change, it only repairs runtime (flannel / `spec.stop` / join ports) and does **not** roll Hagga. `.wslconfig` is left alone when it already has mirrored networking and `autoMemoryReclaim=disabled`, so a healthy re-run does **not** `wsl --shutdown`.

**If it tells you to reboot:** Windows needed a restart to finish enabling WSL. Reboot, then run `Install.bat` as administrator again. Do not install WSL yourself. Your `dune-install.config.ps1` is already there.

**If it says it created `dune-install.config.ps1` and stopped:** that is expected on a first click with no config. Edit the file (step 3) and run `Install.bat` again.

Watch `install-dune-battlegroup.log` in this folder if the window is hard to read. The installer redacts JWT-looking text in the log.

Manual equivalent (elevated PowerShell in this folder):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneBattlegroup.ps1"
```

## 5. Windows Firewall (you do this)

The installer **does not** change Windows Firewall. It **does** open the separate WSL Hyper-V firewall that WSL2 uses on Home.

If Windows Firewall is on (it usually is) and clients cannot join, allow **inbound** on the host. In the **same elevated PowerShell** window, you can run:

```powershell
New-NetFirewallRule -DisplayName "Dune WSL UDP game" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 7777-7810,7888-7941
New-NetFirewallRule -DisplayName "Dune WSL TCP join" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 31982,31519,18888,18889
```

Or: Windows Security → Firewall & network protection → Advanced settings → Inbound Rules, and allow those ports yourself.

## 6. Internet players (port forwarding)

LAN-only: skip this. Internet: on the router, forward to the host’s **`LanIp`**:

| Protocol | Ports | Why |
| --- | --- | --- |
| UDP | `7777–7810` | Game (Funcom official) |
| UDP | `7888–7941` | IGW (this WSL stack; Funcom’s Hyper-V VM does not list these) |
| TCP | `31982` | Join / AMQP (Funcom official) |
| TCP | `31519` | Director (this WSL stack; Funcom’s Hyper-V VM does not list this) |

Funcom’s own docs only mention UDP `7777–7810` and TCP `31982`. Keep those. This WSL install also binds director `31519` and IGW UDP `7888+`; internet clients time out if those are missing.

Set `AdvertiseIp = "auto"` (or paste the current public IPv4), then re-run the installer so **both** Funcom’s listing **and** Unreal `-ExternalAddress` use that address. Bind stays `LanIp`. It does **not** need to be a static IP from the ISP. If the WAN address changes later, run `"auto"` again, or run `Restart-DuneBattlegroup.ps1` (public mode re-looks up ipify).

A listing you can see with **connection timed out** usually means the phone book is public but the game process is still telling clients to UDP to `LanIp`. `Get-DuneStatus.ps1` should show `running_ExternalAddress` equal to the public IPv4, and `running_MultiHome` equal to `LanIp`.

Do **not** port-forward TCP `18888` (Funcom file browser) or TCP `18889` (this pack’s LAN web admin) unless you intend to expose those admin UIs to the internet.

If the ISP uses CGNAT (no real public IPv4 at all), forwarding will not reach the host. LAN play still works (`AdvertiseIp` empty).

House PCs plus internet friends: keep `AdvertiseIp` public, then install `lan-redirect` on each house gaming PC ([House PCs](#house-pcs-when-the-listing-is-public)). Do not run that helper on the host.

## 7. Join from another computer

1. On a **different** computer (LAN or internet), launch Dune: Awakening **Experimental**.
2. Open the self-host / Experimental server list.
3. Find the name you set as `WorldName`.
4. Connect. Client and server must be on the same game version.

**Do not join from the host.** Mirrored WSL networking does not hairpin reliably; the list can spin forever if you try.

If you play from **another PC in the house** and the listing is your public IP, install `lan-redirect` on that PC first ([section 8](#house-pcs-when-the-listing-is-public)). Otherwise the client hairpins through the router and often rubberbands.

If the tab spins after you click the world, Hagga is usually still starting. On the host, run `Get-DuneStatus.ps1`. Join only when **Survival_1** is `Running` / `true`, not `PostLandscapePhysics`, and not while Gateway is `Modifying`. That can take several minutes after the installer finishes, and again after a depot update.

**In queue and the world also shows offline.** The listing is still in Funcom’s directory, but Survival is not Ready yet or director TCP `31519` is not bound. Wait until `Get-DuneStatus.ps1` shows both maps Running / true and `31519` listening. Join only from another computer.

## 8. House PCs when the listing is public

Funcom’s Experimental list has **one** IPv4. There is no “connect by IP” box. If that IPv4 is your WAN address, a PC in the same house still sends UDP/TCP to the public IP and the router has to hairpin it back to `LanIp`. Hagga then logs the client as your WAN address. Unreal rejects late `ServerMove` packets (about a second old), which feels like rubberbanding. The world can be healthy, CPU idle, and internet players fine.

ARK / Valheim / 7DTD often survive that hairpin on the same router because they listen more loosely. This stack is Unreal inside WSL2, and Funcom will not take a LAN address *and* a public one.

**Fix (gaming PC only, not the host):** copy the `lan-redirect` folder. The host installer writes `lan-redirect\dune-client.config.ps1` with `LanIp` for you. On the house PC:

1. Copy `dune-client.config.example.ps1` to `dune-client.config.ps1` if that file is missing, and set `LanIp` to the host Ethernet/Wi-Fi IPv4.
2. Elevated PowerShell in that folder:
   - One-off, window stays open: `Start-DuneLanRedirect.bat`
   - Hibernate until Dune is running: `Start-DuneLanRedirect.bat watch`
   - Daily, quiet: `Install-DuneLanRedirect.ps1` (logon task). `Install-DuneLanRedirect.ps1 -Service` if the person who plays is not a daily Administrator.
3. If you were already in the world, leave to the server list, then join again after the redirector is up (or after `-WatchDune` has armed).
4. On the **host**, `Get-DuneNetHealth.ps1` (optional `-WatchSeconds 60`). The house PC should show RemoteAddr as `lan` (`192.168.x`), not `hairpin-or-self-wan`. `timestamp_expired_count` in the last 2 minutes should stay near 0 while you move.

Uninstall with `Uninstall-DuneLanRedirect.ps1`. Details, ports, and WinDivert notes: `lan-redirect/README.md`. Needs 64-bit PowerShell as Administrator on the gaming PC. Do not install it on the Dune host.

## 9. Keep it running and patched

From PowerShell in this folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It always **looks**: Steam public buildid for app `4754530`, map Ready, join TCP `31982` / `31519`, advertise IPv4. It only **acts** when something is wrong or newer:

- Steam depot download + map roll only if the public buildid differs from the installed appmanifest, or there is no local manifest.
- `battlegroup start` only if Survival/Overmap are not Running 1/1.
- Advertise/listing patch (and a map roll) only if the public IPv4 actually changed.
- Join/director bind only if those ports are missing.
- Helper files are recopied only when they differ; the LAN admin is restarted only when those files changed (or the service was down).
- `wsl --shutdown` only if `.wslconfig` needed `autoMemoryReclaim=disabled`, or `wsl.exe` is wedged.

A no-op hour is about 1–2 minutes. A real patch can take around 45 minutes. After a patch it waits until Gateway is Healthy and both maps stay Running / true, then binds join ports. Output goes to `restart-dune-battlegroup.log`.

It also restores flannel/`spec.stop` if a Windows reboot left the world Stopped.

**Scheduled task (recommended):** elevated PowerShell in this folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledMaintain.ps1"
```

That registers **DuneBattlegroupMaintain**: Daily **6:00 AM** local, repeat **every hour**, plus **At log on** for the Windows user who ran it. **Start in** is this folder. If a run is already going, the next tick is skipped (a depot apply can take ~45 minutes). After a host reboot, At log on brings k3s, Hagga, and join ports back without downloading the depot again. Hourly Steam checks catch an Experimental patch soon after Funcom ships it, so players are not stuck on an old build until the next morning.

Uninstall: `.\Install-DuneScheduledMaintain.ps1 -Uninstall`. If a hand-made task already runs `Restart-DuneBattlegroup.ps1` (any name, any folder), this installer removes it and registers **DuneBattlegroupMaintain** pointed at this folder, so hourly does not copy a stale sibling tree over live admin.

**Join/admin health (every 5 minutes):** a separate task rebinds LAN TCP `31982` / `31519` / `18888` if a `kubectl port-forward` died, and starts `dune-admin.service` if it is down. If Survival and Overmap **pods are missing** (or k3s has no world namespace), it runs `dune-ensure-runtime.sh` (flannel / `spec.stop` / start). It does **not** query Steam, apply a depot, refresh advertise IP, or rewrite FLS DNS. Pods present but not Ready is a log line only. If home WAN is down (no TCP 443 to `1.1.1.1` / `8.8.8.8`), it still does local binds and runtime restore, and it will not touch Funcom listing/FLS. It skips the tick while hourly maintain is running. Log: `repair-dune-health.log`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneScheduledHealth.ps1"
```

Uninstall: `.\Install-DuneScheduledHealth.ps1 -Uninstall`. After an ISP outage, leave advertise/IP refresh to the next hourly maintain (a 5-minute advertise patch would roll maps).

To see if the world is joinable without rolling maps:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneStatus.ps1"
```

To see whether a house client is hairpinning or rubberbanding (`ServerMove TimeStamp expired`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneNetHealth.ps1"
```

If the host has more than one WSL distro, keep `Distro = "Ubuntu"` in the config (the installer sets that distro as default).

## 10. Web admin (LAN browser)

The installer starts a token-gated admin on **`http://<LanIp>:18889`** (LAN only; do not port-forward it). Full tabs, character sheet, GM commands, and safety notes: **[ADMIN-PANEL.md](ADMIN-PANEL.md)**.

1. In WSL: `cat /home/dune/.dune/admin.token` (do not share that file).
2. Paste the token on the login page.
3. Keep Windows Firewall inbound TCP `18889` allowed if you browse from another PC.

The panel binds **only** `LanIp`. Kick/grants/broadcasts use Funcom’s in-cluster RabbitMQ ServerCommand path; “published” means the broker took the message. Restore import overwrites the live world (type `RESTORE`). INI rate changes need Apply UserSettings plus a battlegroup restart.

## Play styles

Set `PlayStyle` **before** the first successful world create. The installer applies Funcom UserSettings at world setup.

**`CasualPve`** copies the bundled `UserEngine.ini`, `UserGame.ini`, and `UserServerCustomSettings.ini`. In short: **NoPVP**, 2× mining, 2.5× global XP, cheaper/faster crafting, slower heat/thirst, less sandworm vehicle grief. The display name is set to your `WorldName`.

Funcom’s file browser (TCP `18888`) often **denies writes** to those inis. The installer chmods the UserSettings volume so the UI can save; if it still cannot, edit the three inis in this folder, copy them over Funcom’s `setup/config` copies inside WSL, then `battlegroup apply-default-usersettings` and a battlegroup restart. Yield/UserSettings never hot-reload.

**`Official`** leaves Funcom’s depot defaults (PvP / security zones as Funcom ships them).

## If something goes wrong

- **“Run this script from an elevated PowerShell window.”** Use `Install.bat` as administrator, or re-open PowerShell as Administrator on the host.
- **WorldName / Region / LanIp errors.** Edit `dune-install.config.ps1`. Region must match the table above exactly. Leave `LanIp` empty to auto-detect, or put the host’s Ethernet/Wi-Fi IPv4 from `ipconfig`.
- **AVX2 error.** That CPU cannot run Funcom’s Unreal server.
- **Reboot / re-run for WSL.** Expected on a host that did not have WSL yet. After Windows comes back, run the installer again; it installs Ubuntu and continues.
- **Virtualization disabled.** Enable VT-x / AMD-V in BIOS/UEFI, then re-run.
- **Ubuntu missing after install.** Reboot if Windows asked, then re-run. Check with `wsl -l -v`.
- **LanIp is not assigned to the host.** Leave `LanIp` empty, or put the IPv4 from `ipconfig` for Ethernet or Wi-Fi.
- **In queue / server offline after an update.** A depot roll restarts Hagga. The client can list the world while Survival is still `Startup` / `PostLandscapePhysics`, or while director `31519` is not listening. Run `Get-DuneStatus.ps1`. Join only when Overmap and Survival_1 are Running / true and Gateway is Ready (not Modifying). `Restart-DuneBattlegroup.ps1` now waits for that and retries the director bind.
- **HP3 / pending connection / could not verify identity.** The Hagga process could not reach Funcom FLS DNS (`sb-retail.fls.funcom.com`). The installer applies a CoreDNS stub and sets game-pod DNS to `8.8.8.8` with `ndots:1`. Re-run `Install.bat` or `Restart-DuneBattlegroup.ps1`. Join only when Survival is Running / true.
- **Client cannot see the world.** Experimental client (not live), same build as the server, firewall, another computer (not the host). For internet: `AdvertiseIp` must be `"auto"` or the current public IPv4, and the router must forward to `LanIp`. For LAN-only: leave `AdvertiseIp` empty.
- **Connection timed out (world is listed).** Funcom’s directory is not the UDP path. The installer must set Unreal `-ExternalAddress` to the public IPv4 while `-MultiHome` stays `LanIp`. `Get-DuneStatus.ps1` shows both. Also forward UDP `7777–7810` **and** TCP `31982` to `LanIp`; this WSL stack also needs TCP `31519` and UDP `7888–7941`. Do not put the WAN IP on k3s as `node-external-ip`.
- **Rubberbanding on a house PC while internet friends are fine.** The listing is the WAN IP, so the LAN client hairpins through the router. `Get-DuneNetHealth.ps1` shows RemoteAddr equal to your public IPv4 and `TimeStamp expired` while you move. Install `lan-redirect` on that gaming PC ([House PCs](#house-pcs-when-the-listing-is-public)). This is not the same as joining from the host.
- **Rubberbanding / hitching for everyone (including internet players).** Windows WSL default `autoMemoryReclaim` (gradual/dropCache) can reclaim Hagga’s pages while the process is running. The installer and `Restart-DuneBattlegroup.ps1` set `autoMemoryReclaim=disabled` in `%USERPROFILE%\.wslconfig`. That key is VM-wide: it applies on the next `wsl --shutdown` (or the first start after the file is written). Re-runs do not shut WSL down when the key is already `disabled`. Do not set `pageReporting` — current WSL rejects it. `Get-DuneStatus.ps1` warns if reclaim is not disabled.
- **WSL distro failed to start.** Often RAM (`WslMemory` too high for the host) or virtualization off.
- **`wsl.exe` Catastrophic failure / `E_UNEXPECTED` while Ubuntu still shows Running.** The WSL control plane wedged; SSH/k3s can still be up. Run `Restart-DuneBattlegroup.ps1`. It terminates the distro, and only `wsl --shutdown`s if exec is still dead.
- **World Stopped after a Windows/WSL reboot.** k3s flannel (`/run/flannel/subnet.env`) is missing and/or Funcom `spec.stop` stayed true (`battlegroup start` can no-op). `Restart-DuneBattlegroup.ps1` restores both, then waits until Survival is Running / true.
- **Join timeout after a depot update; Funcom status says Stopped / no game servers.** A schema util pod can fail on a duplicate patch after the SQL already applied, leaving `DatabaseDeployment` Pending and the director suspended. The maintain job now treats missing Survival/Overmap pods as the source of truth (not the wrapped Funcom CLI table), deletes stuck util pods, and starts maps again.

This installer is meant for a from-scratch Windows 11 Home machine. It will skip world create if a Funcom battlegroup namespace already exists in that Ubuntu. Re-run it anyway to refresh helpers, advertise IP, FLS DNS, join ports, and `.wslconfig` repairs; it stays a no-op for pieces that are already correct.

## License

MIT for the scripts and inis in this repository. Funcom’s dedicated-server depot, operators, and game remain Funcom’s.
