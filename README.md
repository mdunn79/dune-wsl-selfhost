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

The installer must be run from **that** folder. Do not scatter the scripts. If Windows marks the ZIP as blocked, right-click the `.ps1` files → Properties → Unblock, or in PowerShell: `Unblock-File .\*.ps1`.

## 2. Get your Funcom token

1. Sign in at [account.duneawakening.com](https://account.duneawakening.com/).
2. Create or copy the self-host token Funcom shows for your account.
3. Keep it private. Anyone with it can manage your self-host entitlement.

You can paste it into the config file in the next step, or leave that field empty and type it when the installer asks (it will not print the token).

## 3. Create and edit your config

Copy the example, then **change the placeholders** to match the host and the world you want:

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
| `LanIp` | The host’s **LAN IPv4** (Ethernet/Wi-Fi). Traffic binds here. Not `127.0.0.1`. See below. |
| `AdvertiseIp` | Leave `""` for LAN-only. For internet players, the host’s **public WAN IPv4** (what the router forwards to the host). |
| `PlayStyle` | `CasualPve` or `Official`. See [Play styles](#play-styles). |
| `FlsToken` | Your Funcom token in quotes, or `""` to be prompted. |

Optional, but worth checking:

| Field | What it does |
| --- | --- |
| `Distro` | WSL distro name. Leave `Ubuntu` unless the host already has a different Ubuntu name. |
| `WslMemory` | RAM given to WSL. Stay **below** the host’s physical RAM. |
| `WslProcessors` | CPU cores given to WSL. Do not exceed the host’s core count. |
| `WslSwap` | WSL swap size. |

**Finding `LanIp`:** on the host, in PowerShell, run `ipconfig`. Use the IPv4 of Ethernet or Wi-Fi (often `192.168.x.x` or `10.x.x.x`). Skip `127.0.0.1`, the example `192.168.0.10` unless that really is the host, and VPN/virtual adapters. The installer refuses an address that is not assigned to the host.

**Finding `AdvertiseIp`:** LAN-only — leave it empty. Internet — the public IPv4 (router status page, or a “what is my IP” lookup **from the host**). That is the address Funcom gives clients. `LanIp` stays the private address the router forwards **to**.

Do not upload or share `dune-install.config.ps1`. It can hold the Funcom token. The example file in this repo is only a template.

## 4. Run the installer (elevated)

1. On the host, start **Windows PowerShell as Administrator** (Start menu → type PowerShell → right-click **Windows PowerShell** → Run as administrator). A normal (non-admin) window will fail.
2. Change to the folder from step 1, for example:

   ```powershell
   cd C:\dune-wsl-selfhost
   ```

3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneBattlegroup.ps1"
```

The first run can take a long time. The script, in order: enables Windows WSL features **if they are not already on**, installs Ubuntu **if the host has none**, writes `.wslconfig` only when mirrored networking is missing, turns on systemd if needed, opens the WSL Hyper-V firewall if needed, downloads Funcom’s Linux depot with SteamCMD if it is not already there, starts k3s, creates the world, then waits until Overmap and Survival are Ready (up to about 20 minutes on that last wait). Leave the window open.

Re-running is safe. Already-installed WSL, Ubuntu, packages, SteamCMD, the depot, k3s, operators, and an existing world are skipped. It will not wipe operators or recreate the world. If maps are already Ready, it only refreshes join ports.

**If it tells you to reboot:** Windows needed a restart to finish enabling WSL. Reboot, open elevated PowerShell in this folder again, and run the same command. Do not install WSL yourself. Your `dune-install.config.ps1` is already there.

**If it says it created `dune-install.config.ps1` and stopped:** that is expected on a first click with no config. Edit the file (step 3) and run the installer again.

Watch `install-dune-battlegroup.log` in this folder if the window is hard to read. The installer redacts JWT-looking text in the log.

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
| UDP | `7777–7810` | Game |
| UDP | `7888–7941` | IGW (server-to-server / related) |
| TCP | `31982` | Join (AMQP) |
| TCP | `31519` | Director |

Set `AdvertiseIp` to the public WAN IPv4, then re-run the installer so Funcom advertises that address.

Do **not** port-forward TCP `18888` (Funcom file browser) unless you intend to expose that admin UI to the internet.

If the ISP uses CGNAT (no real public IPv4), forwarding will not reach the host. LAN play still works.

People on the same LAN, when `AdvertiseIp` is the WAN IP, usually join through the public listing. That needs NAT loopback on the router; many home routers have it. They still must not join from the host.

## 7. Join from another computer

1. On a **different** computer (LAN or internet), launch Dune: Awakening **Experimental**.
2. Open the self-host / Experimental server list.
3. Find the name you set as `WorldName`.
4. Connect. Client and server must be on the same game version.

**Do not join from the host.** Mirrored WSL networking does not hairpin reliably; the list can spin forever if you try.

First Survival boot can sit in a spinner for several minutes even after the installer reports maps Ready. Wait before assuming it failed.

## 8. Keep it running and patched

From PowerShell in this folder on the host (does not take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It queries Steam for app `4754530`, then updates and rolls maps **only** if a newer public build is waiting or the world is not Ready. A no-op is about 1–2 minutes. A real patch can take around 45 minutes. Output goes to `restart-dune-battlegroup.log`.

Optional: Task Scheduler → At log on → run that same command with **Start in** set to this folder.

If the host has more than one WSL distro, make Ubuntu the default (`wsl --set-default Ubuntu`) so the maintain script finds the `dune` user.

## Play styles

Set `PlayStyle` **before** the first successful world create. The installer applies Funcom UserSettings at world setup.

**`CasualPve`** copies the bundled `UserEngine.ini`, `UserGame.ini`, and `UserServerCustomSettings.ini`. In short: **NoPVP**, 2× mining, 2.5× global XP, cheaper/faster crafting, slower heat/thirst, less sandworm vehicle grief. The display name is set to your `WorldName`. You can change the inis later with Funcom’s file browser (TCP `18888`) and a battlegroup restart.

**`Official`** leaves Funcom’s depot defaults (PvP / security zones as Funcom ships them).

## If something goes wrong

- **“Run this script from an elevated PowerShell window.”** Re-open PowerShell as Administrator on the host.
- **WorldName / Region / LanIp errors.** Edit `dune-install.config.ps1`. Region must match the table above exactly. `LanIp` must be the host’s LAN IPv4.
- **AVX2 error.** That CPU cannot run Funcom’s Unreal server.
- **Reboot / re-run for WSL.** Expected on a host that did not have WSL yet. After Windows comes back, run the installer again; it installs Ubuntu and continues.
- **Virtualization disabled.** Enable VT-x / AMD-V in BIOS/UEFI, then re-run.
- **Ubuntu missing after install.** Reboot if Windows asked, then re-run. Check with `wsl -l -v`.
- **LanIp is not assigned to the host.** Put the IPv4 from `ipconfig` for Ethernet or Wi-Fi, not the example `192.168.0.10` unless that really is the host.
- **Maps not Ready / join spinner.** Wait out the first Survival start (several minutes). Re-run `Restart-DuneBattlegroup.ps1`. Confirm Windows Firewall (step 5) and that you are joining from **another** computer.
- **Client cannot see the world.** Experimental client (not live), same build as the server, firewall, another computer (not the host). For internet: `AdvertiseIp` must be the WAN IPv4 and the router must forward to `LanIp`. For LAN-only: leave `AdvertiseIp` empty and use the real `LanIp`.
- **WSL distro failed to start.** Often RAM (`WslMemory` too high for the host) or virtualization off.

This installer is meant for a from-scratch Windows 11 Home machine. It will skip world create if a Funcom battlegroup namespace already exists in that Ubuntu.

## License

MIT for the scripts and inis in this repository. Funcom’s dedicated-server depot, operators, and game remain Funcom’s.
