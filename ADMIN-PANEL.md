# LAN web admin (TCP 18889)

The WSL self-host pack includes a small Python admin UI for the Funcom battlegroup. The installer and `Restart-DuneBattlegroup.ps1` copy it into `/home/dune/.dune/bin/` and enable `dune-admin.service`.

It binds **only** the host LAN IPv4 (`LanIp`, never `0.0.0.0`). Open it from a browser on the host or another PC on the same LAN. Do **not** port-forward TCP `18889` (or Funcom’s File Browser on `18888`) unless you intend to expose those UIs to the internet.

## Open it

1. URL: `http://<LanIp>:18889` (`LanIp` is in `dune-install.config.ps1`, or `cat /home/dune/.dune/lan-ip.conf` in WSL).
2. Token: `wsl -d Ubuntu -u dune -- cat /home/dune/.dune/admin.token`  
   Do not share that file. The panel does not print Funcom JWT, database, or RabbitMQ passwords.
3. Allow Windows Firewall inbound TCP `18889` if you browse from another LAN PC.

`Get-DuneStatus.ps1` prints the URL when `LanIp` is set. After a helper sync, `systemctl is-active dune-admin.service` should be `active`.

## What it can do

| Tab | Use |
| --- | --- |
| **World** | Joinable status, Survival/Overmap pods, CPU/RAM, Steam local vs public buildid, join ports, advertise vs bind, 15s auto-refresh, start / stop / restart / repair, Postgres backup, restore (type `RESTORE`), timed restart with in-game countdown, File Browser and Director links. Repair skips the FLS DNS rewrite so it will not bounce Hagga. |
| **Players** | Roster including **offline** characters, name/id filter, kick, local ban (optional hours), notes, optional whitelist, broadcast, restart countdown. **Last seen here** is `last_avatar_activity` on this world (not Funcom’s origin `last_login_time`). Empty is **never**; **xfer** means the character was transferred in. |
| **Character** | Sheet for one FLS id: mentor/class and caste, school trainers, vitals (health, water, spice, heat, Eyes of Ibad, map), intel/tech points and recipes, tracked journey, faction standing, guild, inventory, blueprints, Landsraad, respawns, Hagga coordinates. Last seen here is this world’s activity; transferred characters also show the origin last-login stamp. Dune does **not** store a single RPG “level”; Combat/Gathering/Exploration tracks appear when the game has written them. |
| **Tools** | Live GM commands (target should be **online**): grant item, welcome kit, XP, unspent skill points, skill module, refill water, teleport, teleport onto another player, spawn a vehicle. Inventory wipe and progression reset need a confirm. |
| **Settings** | Categorized UserSettings / UserGame / UserEngine rates (harvest, combat, **durability drain vs max-durability repair tax**, survival, storms, Landsraad, building). Discord webhook (`https` only), welcome kit, rotate admin token. Save INIs, then **Apply UserSettings**, then a battlegroup/map restart for rates to load. |
| **Logs** | Survival / Overmap / Director / Gateway / text-router tails. JWT-looking strings are stripped. |
| **Audit** | Local log of panel actions (`admin-audit.jsonl`). |

Funcom does not ship a kick/ban CLI. Kick, grants, broadcasts, and other GM tools go over Funcom’s in-cluster RabbitMQ ServerCommand path (exchange `heartbeats`, routing key `notifications`). **Published** means the broker accepted the message; check in-game that the effect landed.

## Files in this pack

| File | Role |
| --- | --- |
| `dune-admin.py` | HTTP server (stdlib), token auth, kubectl/psql/RabbitMQ ops |
| `dune-admin-lib.py` | Steam/health/net, INI, backups, character intel, extras |
| `dune-admin.html` | Browser UI |
| `dune-admin.sh` | `python3` launcher; `--install` enables/restarts the systemd unit |
| `dune-admin.service` | `User=dune`, `ExecStart=.../dune-admin.sh` |

On the WSL host, bans, whitelist, notes, and panel config live under `/home/dune/.dune/` (`admin-bans.json`, `admin-whitelist.json`, `admin-notes.json`, `admin-config.json`). They are **not** Funcom directory files.

## Safety

- Empty whitelist enable is refused (it would kick everyone online).
- Restore import overwrites the live world; the UI requires the word `RESTORE`.
- Token rotate needs a confirm; copy the new value immediately.
- Apply depot uses the same `dune-maintain.sh` job as the daily scheduled task; maps roll only if a newer Steam depot is waiting.
- The panel will not spawn a vehicle at `0,0,0`.

## If the UI looks wrong

- **“Not joinable”** with maps actually Running: hard-refresh the browser. The panel’s joinable flag is Survival + Overmap `1/1 Running` plus TCP `31982` and `31519`. It is not a Steam update by itself; World shows whether maintain is running.
- **Logs say “no pod”:** the battlegroup namespace was not listed, or that workload is not up. `Get-DuneStatus.ps1` is the source of truth for map Ready.
- **Offline people missing:** the roster is `dune.player_state` joined to `dune.accounts` (FLS hex ids). Online is `online_status` plus Funcom `serverstats` when present.
- **Service down:** in WSL, `/home/dune/.dune/bin/dune-admin.sh --install` (as root or via the restart script). Token file is created if missing; existing tokens are kept.
