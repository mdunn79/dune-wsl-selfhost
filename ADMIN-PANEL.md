# LAN web admin (TCP 18889)

The WSL self-host pack includes a small Python admin UI for the Funcom battlegroup. The installer and `Restart-DuneBattlegroup.ps1` copy it into `/home/dune/.dune/bin/` and enable `dune-admin.service`. `Repair-DuneHealth.ps1` (5-minute task) starts the unit if it died; it does not recopy helpers.

It binds **only** the host LAN IPv4 (`LanIp`, never `0.0.0.0`). Open it from a browser on the host or another PC on the same LAN. Do **not** port-forward TCP `18889` (or Funcom’s File Browser on `18888`) unless you intend to expose those UIs to the internet.

## Open it

1. URL: `http://<LanIp>:18889` (`LanIp` is in `dune-install.config.ps1`, or `cat /home/dune/.dune/lan-ip.conf` in WSL).
2. Token: `wsl -d Ubuntu -u dune -- cat /home/dune/.dune/admin.token`  
   Do not share that file. The panel does not print Funcom JWT, database, or RabbitMQ passwords.
3. Allow Windows Firewall inbound TCP `18889` if you browse from another LAN PC.

`Get-DuneStatus.ps1` prints the URL when `LanIp` is set. After a helper sync, `systemctl is-active dune-admin.service` should be `active`.

**Clocks** in the panel follow the **browser’s time zone** (`Intl` IANA name in the header, e.g. `America/Los_Angeles`). Postgres `timestamptz` strings (`…+00`) and Unix epoch stamps (first-seen, Steam check, INI apply, backups, scheduled restart) are converted with `toLocaleString` plus a short zone label (`PDT`). Naive audit stamps from WSL `strftime` are shown as local wall clock. Public `/status` is unchanged. The schedule picker stays `datetime-local` (already browser-local).

## What it can do

| Tab | Use |
| --- | --- |
| **World** | Joinable status, Survival/Overmap/**Gateway** pods, CR Ready vs Gateway Modifying, Hagga pawn dots and a separate Overmap plot (two coordinate spaces, not mixed), CPU/RAM, Steam installed vs public buildid plus last-check vs depot mtimes, Funcom CR **listing title** vs `Bgd.ServerDisplayName` subtitle, join ports, advertise vs bind, 15s auto-refresh, start / stop / restart / repair, Postgres backup, restore (type `RESTORE`), timed restart with in-game countdown, File Browser, Director, and **public status** (`/status`, no token, no roster names). Repair skips the FLS DNS rewrite so it will not bounce Hagga. **INI drift** vs setup/config and “maps need restart after apply” stamps show here. **Join path** is Survival `LogNet RemoteAddr` connect/error lines (up to 2h), not who is in-game — that is Players → online. On a public world, leave Start / Stop / Restart / Apply depot / Advertise alone unless you intend downtime. **Restart** (button and schedule) is deferred while anyone is online unless you turn that off in Settings. |
| **Players** | Roster including **offline** characters, name/id filter, kick, local ban (optional hours), notes, optional whitelist, broadcast, restart countdown. **Last seen here** is `last_avatar_activity` on this world (not Funcom’s origin `last_login_time`). Empty is **never**; **xfer** means the character was transferred in. **First seen** is when this panel first noticed the character (`admin-presence.json`), not a Funcom field. Discord join/leave (Settings) fire from the same roster. |
| **Character** | Sheet for one FLS id: mentor/class and caste, school trainers, vitals (health, water, spice, heat, Eyes of Ibad, map), intel/tech points and recipes, tracked journey, faction standing, guild, inventory **with catalog labels**, blueprints, Landsraad, respawns, Hagga coordinates, **carried vs bank Solari**. Inventory qty is read-only. Last seen here is this world’s activity; transferred characters also show the origin last-login stamp. First seen is the panel stamp. Dune does **not** store a single RPG “level”; Combat/Gathering/Exploration tracks appear when the game has written them. After a live GM action the sheet is refreshed in the JSON result. |
| **Tools** | Live GM commands (target should be **online**): grant item, welcome kit, XP, unspent skill points, skill module, refill water, teleport, teleport onto another player, spawn a vehicle. **Item catalog** is awakening.wiki `{name, item_id}` cached in `/home/dune/.dune/admin-item-catalog.json`, merged with `SELECT DISTINCT template_id FROM dune.items` on this world. Refresh on demand or when the Steam depot buildid changes — not every World poll. Schematics / recipes / patents are filtered from the wiki dump. Grants still accept a raw FName. **SQL stack edit is not offered** (maps own bags, same as mute DELETE). **Offline-move fallback** is only after they are already offline (type `DC`); it does not kick and does not UDP-drop. **Dry-run** is the header checkbox next to Auto-refresh (on by default, also applies to Broadcast on Players and to World start/stop/restart/apply/advertise). Uncheck it before anything is published to RabbitMQ. Inventory wipe requires typing `WIPE`; progression reset requires `RESET`. Settings **GM gates** can disable grants / wipe / reset / teleport / spawn even when dry-run is off. |
| **Bases** | Read-only list of **buildings** (piece count + most common `building_instances.last_placed_by_player_id`, which is a controller id) and **claims** (Sub-Fief / totem from `permission_actor` rank 1). Blueprints/backups if those tables have rows. Funcom’s `buildings.owner_id` is often null, so that column is not used. SELECT only. **Delete queue** is a local reminder JSON; Apply refuses live SQL DELETE because maps hold objects in memory. |
| **Vehicles** | Read-only `dune.vehicles` joined to `actors` for class/map. Owner is `permission_actor_rank` rank 1, else `recovered_vehicles.character_id`. Abandoned world bikes with no rank show **unowned / world**, not a fake missing player. SELECT only. |
| **Social** | Read-only CHOAM board (`dune_exchange_orders`), guilds/members/invites, Landsraad term/decrees/current-term tasks, and carried vs bank Solari. Empty CHOAM/bank is normal until the world has listings. SELECT only. There is no Funcom whisper/chat table on this host. |
| **Settings** | Categorized UserSettings / UserGame / UserEngine rates (harvest, combat, **durability drain vs max-durability repair tax**, survival, storms, Landsraad, building, **pings**, **recustomize Solaris**, **guild cap**, reconnect grace, CHOAM listing fees). Listing **title** is Funcom CR `spec.title` (read-only here; changing it can bounce maps). **Subtitle** is `Bgd.ServerDisplayName`. Shows File Browser vs `setup/config` **drift**. Discord webhook (`https` only) with join / leave / maps-not-Ready flags, welcome kit, rotate admin token, GM gates, **defer restart if anyone is online** (on by default). Save INIs, then **Apply UserSettings**, then a battlegroup/map restart for rates to load. Apply + restart are downtime; skip them on a public world unless you mean to. |
| **Logs** | Survival / Overmap / Director / Gateway / text-router tails. JWT-looking strings are stripped. |
| **Audit** | Local log of panel actions (`admin-audit.jsonl`). |

Funcom does not ship a kick/ban CLI. Kick, grants, broadcasts, and other GM tools go over Funcom’s in-cluster RabbitMQ ServerCommand path (exchange `heartbeats`, routing key `notifications`). **Published** means the broker accepted the message; check in-game that the effect landed. Broadcast is a title-card popup (`BroadcastPayload` + `LocalizedText`), not chat.

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
- **Dry-run** (Tools, on by default) returns a preview and does **not** publish ServerCommands, apply UserSettings, restart maps, advertise, restore, or start a depot maintain.
- Wipe inventory / reset progression also need the literal phrases `WIPE` / `RESET`.
- Bases, vehicles, and Social tabs only `SELECT`; they never `UPDATE` or `DELETE`. The delete queue is a local reminder; Apply will not run mute SQL deletes. Inventory qty / stack edit is the same: no SQL UPDATE of `dune.items`.
- Item picker is a **cached** community wiki list plus FNames already instanced on this world. It is not Funcom’s master catalog and not unpacked `.pak` data. Refresh the cache from Tools; the picker still works from the last JSON if awakening.wiki is down.
- Friends on the LAN can open `http://<LanIp>:18889/status` (or `/status.json`) with **no token**. It shows joinable, online count, and map Ready only — no roster names, no GM. Do **not** port-forward 18889.
- **Restart defer** (Settings, on by default) refuses World Restart and postpones a scheduled restart while the roster has anyone online. Uncheck it only if you intend to bounce maps under players. Discord join/leave/map-down follow the Settings checkboxes; there is no Funcom whisper ServerCommand.

## If the UI looks wrong

- **“Not joinable”** with pods `1/1 Running`: kubectl is not the join check. Joinable is Funcom Survival_1 + Overmap **Running / true**, Gateway not Modifying, plus TCP `31982` / `31519`. `Startup` / `PostLandscapePhysics` is offline for clients even when pods look Ready. World shows whether maintain is running. `Get-DuneStatus.ps1` is the same Funcom table.
- **Logs say “no pod”:** the battlegroup namespace was not listed, or that workload is not up. `Get-DuneStatus.ps1` is the source of truth for map Ready.
- **Offline people missing:** the roster is `dune.player_state` joined to `dune.accounts` (FLS hex ids). Online is `online_status` plus Funcom `serverstats` when present. LAN-redirect does not hide you; it only rewrites the join IP. The world-owner account on this host often has the world HostId in `accounts.user`; the panel lists that character by Funcom id (`name#digits`) instead, and Tools accepts that id. Clear the Players filter if it still has the HostId.
- **Join path empty while you are in-game:** Unreal only writes `RemoteAddr` on connect/errors. A stable session often has none. Players → online is the live roster. Rubberband `TimeStamp expired` is still a 15-minute count from those logs.
- **Service down:** in WSL, `/home/dune/.dune/bin/dune-admin.sh --install` (as root or via the restart script). Token file is created if missing; existing tokens are kept.
