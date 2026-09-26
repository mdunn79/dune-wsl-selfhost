# Dune: Awakening self-host on Windows 11 Home (WSL)

Runs Funcom’s **Linux** battlegroup inside WSL2. It does **not** use Funcom’s Hyper-V VM, Hyper-V Manager, or Windows 11 Pro.

**The host** is the Windows 11 PC where you run this installer — your machine, not anyone else’s. Players can join from the LAN or from the internet if you port-forward. Do **not** join the world from the host itself (WSL mirrored networking does not hairpin).

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
| `AdvertiseIp` | Leave `""` for LAN-only (typical). Funcom does **not** need a static ISP address. Internet: `"auto"` looks up the **current** public IPv4 at install time. |
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

**Finding `AdvertiseIp`:** LAN-only — leave it empty. Funcom then lists `LanIp`. Internet is optional: set `AdvertiseIp = "auto"` so the installer looks up the current public IPv4 (a “what is my IP” result, not a static assignment). That address is written in **two** places: Funcom’s directory (`HOST_DATACENTER_IP_ADDRESS`) and Unreal `-ExternalAddress`. The game still **binds** `LanIp`. Funcom’s directory stores a literal IPv4; it does not take a hostname or DDNS name. If the ISP later changes the address, set `"auto"` again and re-run, or let `Restart-DuneBattlegroup.ps1` refresh it. `LanIp` stays the private address the router forwards **to**.

Do **not** set k3s `node-external-ip` to the WAN address on WSL. Funcom’s Alpine VM can; WSL’s k3s agent then dials `WAN:6443` and the cluster wedges. This installer never does that.

Do not upload or share `dune-install.config.ps1`. It can hold the Funcom token. The example file in this repo is only a template.

## 4. Run the installer (elevated)

1. Right-click **`Install.bat`** → **Run as administrator**. (Double-click also works; it will prompt for elevation.) A normal non-admin window will fail.
2. Leave the window open. The first run can take a long time.

The script, in order: enables Windows WSL features **if they are not already on**, installs Ubuntu **if the host has none**, writes `.wslconfig` only when mirrored networking is missing, turns on systemd if needed, opens the WSL Hyper-V firewall if needed, downloads Funcom’s Linux depot with SteamCMD if it is not already there, starts k3s, creates the world, then waits until Overmap **and** Survival stay Ready (up to about 20 minutes on that last wait). Survival often SIGSEGVs once on first boot and comes back; the installer waits through that.

Re-running is safe. Already-installed WSL, Ubuntu, packages, SteamCMD, the depot, k3s, operators, and an existing world are skipped. It will not wipe operators or recreate the world. If maps are already Ready, it only refreshes join ports.

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
New-NetFirewallRule -DisplayName "Dune WSL TCP join" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 31982,31519,18888
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

Do **not** port-forward TCP `18888` (Funcom file browser) unless you intend to expose that admin UI to the internet.

If the ISP uses CGNAT (no real public IPv4 at all), forwarding will not reach the host. LAN play still works.

People on the same LAN, when `AdvertiseIp` is the WAN IP, usually join through the public listing. That needs NAT loopback on the router; many home routers have it. They still must not join from the host.

## 7. Join from another computer

1. On a **different** computer (LAN or internet), launch Dune: Awakening **Experimental**.
2. Open the self-host / Experimental server list.
3. Find the name you set as `WorldName`.
4. Connect. Client and server must be on the same game version.

**Do not join from the host.** Mirrored WSL networking does not hairpin reliably; the list can spin forever if you try.

If the tab spins after you click the world, Hagga is usually still starting. On the host, run `Get-DuneStatus.ps1`. Join only when **Survival_1** is `Running` / `true`, not `PostLandscapePhysics`, and not while Gateway is `Modifying`. That can take several minutes after the installer finishes, and again after a depot update.

**In queue and the world also shows offline.** The listing is still in Funcom’s directory, but Survival is not Ready yet or director TCP `31519` is not bound. Wait until `Get-DuneStatus.ps1` shows both maps Running / true and `31519` listening. Join only from another computer.

## 8. Keep it running and patched

From PowerShell in this folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It queries Steam for app `4754530`, then updates and rolls maps **only** if a newer public build is waiting or the world is not Ready. After a real patch it waits until Gateway is Healthy and both maps stay Running / true (old pods still showing Running during Modifying are ignored), then binds join TCP `31982` / `31519`. A no-op is about 1–2 minutes. A real patch can take around 45 minutes. Output goes to `restart-dune-battlegroup.log`.

Optional: Task Scheduler → At log on → run `Restart-DuneBattlegroup.ps1` with **Start in** set to this folder.

To see if the world is joinable without rolling maps:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Get-DuneStatus.ps1"
```

If the host has more than one WSL distro, keep `Distro = "Ubuntu"` in the config (the installer sets that distro as default).

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
- **WSL distro failed to start.** Often RAM (`WslMemory` too high for the host) or virtualization off.

This installer is meant for a from-scratch Windows 11 Home machine. It will skip world create if a Funcom battlegroup namespace already exists in that Ubuntu.

## License

MIT for the scripts and inis in this repository. Funcom’s dedicated-server depot, operators, and game remain Funcom’s.
