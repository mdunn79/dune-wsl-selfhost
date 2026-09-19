# Dune: Awakening self-host on Windows 11 Home (WSL)

Runs Funcom’s Linux battlegroup inside WSL2. Does **not** use Hyper-V or Windows 11 Pro.

**Needs:** current Windows 11, AVX2 CPU, ~32 GB RAM for WSL, a Funcom self-host token from [account.duneawakening.com](https://account.duneawakening.com/). LAN play.

## Install

1. Copy `dune-install.config.example.ps1` to `dune-install.config.ps1`. Set `WorldName`, `Region`, `LanIp` (this PC’s IPv4), `PlayStyle` (`CasualPve` or `Official`), and `FlsToken`.
2. Elevated PowerShell in this folder:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-DuneBattlegroup.ps1"
   ```

3. If **Windows Firewall** is on, allow inbound UDP `7777-7810` and `7888-7941`, TCP `31982`, `31519`, `18888`. This script does not change Windows Firewall.
4. Join from **another** LAN PC (Experimental / self-host tab), same game version. Do not join from this Windows host.

## Afterward

Optional daily check (updates only if Steam has a new depot):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Restart-DuneBattlegroup.ps1"
```

Do not commit `dune-install.config.ps1` (it holds your token).
