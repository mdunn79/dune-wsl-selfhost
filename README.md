# Dune: Awakening self-host on Windows 11 Home (WSL)

Runs Funcom’s **Linux** battlegroup inside WSL2. It does **not** use Funcom’s Hyper-V VM, Hyper-V Manager, or Windows 11 Pro.

Players join over the LAN. Do not join from the same Windows PC that is hosting the world.

The scripts in this folder are MIT. The game files SteamCMD downloads are Funcom’s; this pack does not redistribute them.

## What you need

- Windows 11 (Home is fine). You do **not** need WSL or Ubuntu already installed — the installer turns on the Windows WSL features, installs Ubuntu, and configures WSL2 (mirrored networking, systemd, WSL firewall).
- CPU with **AVX2** (Funcom’s Unreal requirement).
- Enough RAM that you can give WSL a large allocation and still leave several GB for Windows. Funcom’s self-host wants a lot of RAM; **32 GB for WSL** is the default in the example config. On a 32 GB PC, lower `WslMemory` (for example `24GB`). On 64 GB, `32GB` is comfortable.
- Disk space for Ubuntu, k3s, and the Linux Steam depot (plan on tens of GB).
- A wired or Wi-Fi LAN. Clients must be other PCs on that network.
- A Funcom **self-host token** from [account.duneawakening.com](https://account.duneawakening.com/).
- The **Dune: Awakening Experimental** client on every machine that will play. The client build must match the Linux depot this installer downloads.

You do **not** need: WSL preinstalled, Ubuntu preinstalled, Windows 11 Pro, Hyper-V Manager, Funcom’s Windows SteamCMD `installdune.bat`, or a Steam account for the dedicated server (SteamCMD uses anonymous login).

Windows itself may require **one reboot** the first time those WSL features are enabled. That is a Windows limit, not a manual WSL install. After reboot, run the same installer command again; it continues from there.

## 1. Put this folder on the host PC

Download the files and keep them together in one directory, for example `C:\dune-wsl-selfhost`. The installer must be run from **that** folder. Do not scatter the scripts.

## 2. Get your Funcom token

1. Sign in at [account.duneawakening.com](https://account.duneawakening.com/).
2. Create or copy the self-host token Funcom shows for your account.
3. Keep it private. Anyone with it can manage your self-host entitlement.

You can paste it into the config file in the next step, or leave that field empty and type it when the installer asks (it will not print the token).

## 3. Create and edit your config

Copy the example, then **change the placeholders to your world**:

```powershell
copy .\dune-install.config.example.ps1 .\dune-install.config.ps1
notepad .\dune-install.config.ps1
```

If you run the installer with no `dune-install.config.ps1`, it copies the example for you and **stops**, so you can edit it and run again.

Fill in at least these:

| Field | What to put |
| --- | --- |
| `WorldName` | The name players see in the self-host list. No `'` or `\|`. Example: `"My Sietch"`. |
| `Region` | Exactly one of: `Asia`, `Europe`, `North America`, `Oceania`, `South America`. This is Funcom’s region menu, not your Windows locale. |
| `LanIp` | This host PC’s **LAN IPv4**, not `127.0.0.1`. See below. |
| `PlayStyle` | `CasualPve` or `Official`. See [Play styles](#play-styles). |
| `FlsToken` | Your Funcom token in quotes, or `""` to be prompted. |

Optional, but worth checking:

| Field | What it does |
| --- | --- |
| `Distro` | WSL distro name. Leave `Ubuntu` unless you already installed a different Ubuntu name. |
| `WslMemory` | RAM given to WSL. Stay **below** physical RAM. |
| `WslProcessors` | CPU cores given to WSL. Do not exceed this PC’s cores. |
| `WslSwap` | WSL swap size. |

**Finding `LanIp`:** in PowerShell, run `ipconfig`. Use the IPv4 of Ethernet or Wi-Fi on this LAN (often `192.168.x.x` or `10.x.x.x`). Skip `127.0.0.1` and virtual adapters you do not use for play.

**Do not share** `dune-install.config.ps1`. It can hold your token. The example file in this repo is only a template.

## 4. Run the installer (elevated)

1. Start **Windows PowerShell as Administrator** (right-click → Run as administrator).
2. `cd` into this folder.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneBattlegroup.ps1"
```

The first run can take a long time. The script, in order: enables Windows WSL features **if they are not already on**, installs Ubuntu **if this PC has none**, writes `.wslconfig` only when mirrored networking is missing, turns on systemd if needed, opens the WSL Hyper-V firewall if needed, downloads Funcom’s Linux depot with SteamCMD if it is not already there, starts k3s, creates the world, then waits until Overmap and Survival are Ready (up to about 20 minutes on that last wait). Leave the window open.

Re-running is safe. Already-installed WSL, Ubuntu, packages, SteamCMD, the depot, k3s, operators, and an existing world are skipped. It will not wipe operators or recreate the world. If maps are already Ready, it only refreshes join ports.

**If it tells you to reboot:** Windows needed a restart to finish enabling WSL. Reboot, open elevated PowerShell in this folder again, and run the same command. Do not install WSL yourself. Your `dune-install.config.ps1` is already there.

**If it says it created `dune-install.config.ps1` and stopped:** that is expected on a first click with no config. Edit the file (step 3) and run the installer again.

Watch `install-dune-battlegroup.log` in this folder if the window is hard to read. The installer redacts JWT-looking text in the log.

## 5. Windows Firewall (you do this)

The installer **does not** change Windows Firewall. It **does** open the separate WSL Hyper-V firewall that WSL2 uses on Home.

If Windows Firewall is on and LAN clients cannot join, allow **inbound** on this host:

- UDP `7777–7810` and `7888–7941` (game / IGW)
- TCP `31982` (join), `31519` (Director), `18888` (File Browser)

Windows Security → Firewall & network protection → Advanced settings → Inbound Rules, or equivalent `New-NetFirewallRule` commands you run yourself.

You do **not** need to port-forward on the router for LAN-only play.

## 6. Join from another PC

1. On a **different** computer on the same LAN, launch Dune: Awakening **Experimental**.
2. Open the self-host / Experimental server list.
3. Find the name you set as `WorldName`.
4. Connect. Client and server must be on the same game version.

**Do not join from this Windows host.** Mirrored WSL networking does not hairpin reliably; the list can spin forever if you try.

First Survival boot can sit in a spinner for several minutes even after the installer reports maps Ready. Wait before assuming it failed.

## 7. Keep it running and patched

From PowerShell in this folder (does not need to take the world down if Steam has no new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

It queries Steam for app `4754530`, then updates and rolls maps **only** if a newer public build is waiting or the world is not Ready. A no-op is about 1–2 minutes. A real patch can take around 45 minutes. Output goes to `restart-dune-battlegroup.log`.

Optional: Task Scheduler → At log on → run that same command with **Start in** set to this folder.

If you have more than one WSL distro, make Ubuntu the default (`wsl --set-default Ubuntu`) so the maintain script finds the `dune` user.

## Play styles

Set `PlayStyle` **before** the first successful world create. The installer applies Funcom UserSettings at world setup.

**`CasualPve`** copies the bundled `UserEngine.ini`, `UserGame.ini`, and `UserServerCustomSettings.ini`. In short: **NoPVP**, 2× mining, 2.5× global XP, cheaper/faster crafting, slower heat/thirst, less sandworm vehicle grief. The display name is set to your `WorldName`. You can change the inis later with Funcom’s file browser (TCP `18888`) and a battlegroup restart.

**`Official`** leaves Funcom’s depot defaults (PvP / security zones as Funcom ships them).

## If something goes wrong

- **“Run this script from an elevated PowerShell window.”** Re-open PowerShell as Administrator.
- **WorldName / Region / LanIp errors.** Edit `dune-install.config.ps1`. Region must match the table above exactly. LanIp must be this PC’s LAN IPv4.
- **AVX2 error.** This CPU cannot run Funcom’s Unreal server.
- **Reboot / re-run for WSL.** Expected on a PC that did not have WSL yet. After Windows comes back, run the installer again; it installs Ubuntu and continues.
- **Ubuntu missing after install.** Re-run the installer (it runs `wsl --install -d Ubuntu`). If it still fails, `wsl -l -v` and try once more.
- **Maps not Ready / join spinner.** Wait out the first Survival start. Re-run `Restart-DuneBattlegroup.ps1`. Confirm Windows Firewall (step 5) and that you are joining from another PC.
- **Client cannot see the world.** Same Experimental build, correct `LanIp`, firewall, other PC on the same LAN.

This installer is meant for a from-scratch Home box. It will skip world create if a Funcom battlegroup namespace already exists in that Ubuntu.

## License

MIT for the scripts and inis in this repository. Funcom’s dedicated-server depot, operators, and game remain Funcom’s.
