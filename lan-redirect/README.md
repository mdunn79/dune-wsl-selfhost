# Dune LAN redirect (gaming PC)

Funcom's listing only has the public IPv4. This PC intercepts those Dune ports and rewrites them to the host LAN IP. Hagga then sees `192.168.x` instead of the WAN address.

Run this on the **gaming PC**, not on the host. Start the redirector (or wait until `-WatchDune` arms), then join from the **Experimental** tab in the server browser (player-run worlds). If you were already in the world, leave to the list and join again.

## Run by hand (no background install)

Elevated cmd or PowerShell in this folder. Copy `dune-client.config.example.ps1` to `dune-client.config.ps1` and set `LanIp` first (or pass `-LanIp 192.168.1.101`).

Always on until you close the window:

```text
Start-DuneLanRedirect.bat
```

or

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-DuneLanRedirect.ps1
```

Hibernate until Dune starts, then arm, then sleep again when the client exits:

```text
Start-DuneLanRedirect.bat watch
```

or

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-DuneLanRedirect.ps1 -WatchDune
```

Leave that window open. Ctrl+C when you are done. `-VerbosePackets` prints per-packet counters.

## Daily install (quiet)

Still a small watcher at logon (or a service), but WinDivert is only open while the Dune client process is running. That is the default for both `Install-DuneLanRedirect.ps1` and `Install-DuneLanRedirect.ps1 -Service`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-DuneLanRedirect.ps1
```

Log: `logs\redirect.log` in this folder (same place as the WinSW wrapper `.out.log` / `.err.log` when using `-Service`).

If the person who plays is not a daily Administrator:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-DuneLanRedirect.ps1 -Service
```

Remove either, then close any hand-run redirect window. That also stops the WinDivert driver so Explorer can delete this folder (`WinDivert64.sys` stays locked while the driver is loaded):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-DuneLanRedirect.ps1
```

Ctrl+C on a hand-run window now unloads the driver too. If a copy is still locked, `sc stop WinDivert` from an elevated prompt, then delete.

## Host-side check

`Get-DuneNetHealth.ps1` on the host. House PC should be `lan`. `timestamp_expired_count` in the last 2 minutes should stay near 0 while you move.

## Ports

UDP 7777-7810, UDP 7888-7941, TCP 31982, TCP 31519. Not 18888.

## If WinDivertOpen fails

Need 64-bit PowerShell as Administrator. Win32 577 means the driver was blocked (Smart App Control / core isolation).
