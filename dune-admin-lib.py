"""Extra Dune admin APIs. bind() attaches helpers onto the main module."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

M = None
CONFIG_FILE = NOTES_FILE = WELCOME_FILE = None
SETUP_CFG = Path("/home/dune/.dune/download/scripts/setup/config")
MANIFEST = Path("/home/dune/.dune/download/steamapps/appmanifest_4754530.acf")
APPINFO = Path("/home/dune/.dune/last-appinfo.txt")
WSLCONFIG = Path("/mnt/c/Users/mdunn/.wslconfig")
_NET_CACHE = {"t": 0.0, "v": {}}
_HEALTH_CACHE = {"t": 0.0, "v": {}}
_LAST_ONLINE: set = set()
_WAS_JOINABLE = False
_ONLINE_READY = False

INI_KEYS = [
    ("UserServerCustomSettings.ini", "PVPMode"),
    ("UserServerCustomSettings.ini", "GatheringAmount"),
    ("UserServerCustomSettings.ini", "CraftingCost"),
    ("UserServerCustomSettings.ini", "WaterExtractionRate"),
    ("UserServerCustomSettings.ini", "CraftingTimeMultiplier"),
    ("UserServerCustomSettings.ini", "LootRespawnSpeed"),
    ("UserServerCustomSettings.ini", "BuildingCostMultiplier"),
    ("UserServerCustomSettings.ini", "ResourceRespawnSpeed"),
    ("UserServerCustomSettings.ini", "FuelBurnTimeMultiplier"),
    ("UserServerCustomSettings.ini", "InventoryVolumeMultiplier"),
    ("UserServerCustomSettings.ini", "PlayerDamageToPlayer"),
    ("UserServerCustomSettings.ini", "GlobalXpMultiplier"),
    ("UserServerCustomSettings.ini", "CombatXp"),
    ("UserServerCustomSettings.ini", "GatheringXp"),
    ("UserServerCustomSettings.ini", "HeatBuildupRate"),
    ("UserServerCustomSettings.ini", "ThirstMultiplier"),
    ("UserServerCustomSettings.ini", "LandsraadContributionMultiplier"),
    ("UserServerCustomSettings.ini", "BaseBackupToolTimeRestriction"),
    ("UserServerCustomSettings.ini", "PlayerDeathLootRule"),
    ("UserServerCustomSettings.ini", "DropEquipmentOnDeath"),
    ("UserServerCustomSettings.ini", "SandwormConsequences"),
    ("UserGame.ini", "m_MaxNumLandclaimSegments"),
    ("UserGame.ini", "m_bShouldForceEnablePvpOnAllPartitions"),
    ("UserGame.ini", "m_bAreSecurityZonesEnabled"),
    ("UserGame.ini", "m_BaseBackupToolTimeRestrictionInSeconds"),
    ("UserEngine.ini", "Dune.GlobalMiningOutputMultiplier"),
    ("UserEngine.ini", "Dune.GlobalVehicleMiningOutputMultiplier"),
    ("UserEngine.ini", "Bgd.ServerDisplayName"),
    ("UserEngine.ini", "sandworm.dune.Enabled"),
    ("UserEngine.ini", "Sandstorm.Enabled"),
]

CATALOG = [
    ("Water", "Water"),
    ("Solari", "Solari"),
    ("Dew reaper", "DewReaper"),
    ("Fuel cell", "FuelCell"),
    ("Welding wire", "WeldingWire"),
    ("Spice melange", "SpiceMelange"),
    ("Complex machinery T2", "T2MachineComponent"),
    ("Complex machinery T3", "T3MachineComponent"),
    ("Complex machinery T4", "T4MachineComponent"),
    ("Complex machinery T5", "T5MachineComponent"),
    ("Complex machinery T6", "T6MachineComponent"),
    ("Advanced servok", "AdvancedServok"),
    ("Particle capacitor", "ParticleCapacitor"),
    ("Carbide scraps", "CarbideScraps"),
    ("Plastanium ingot", "PlastaniumIngot"),
    ("Iron ingot", "IronIngot"),
    ("Steel ingot", "SteelIngot"),
    ("Copper ingot", "CopperIngot"),
    ("Aluminum ingot", "AluminumIngot"),
    ("Cobalt paste", "CobaltPaste"),
    ("Spice-infused dust", "SpiceInfusedDust"),
    ("Healkit", "Healkit"),
    ("Stilltent", "Stilltent"),
    ("Compactor", "Compactor"),
    ("Cutteray", "Cutteray"),
    ("Binoculars", "Binoculars"),
    ("Holster", "Holster"),
    ("Power pack (small)", "PowerPackSmall"),
    ("Blood purifier", "BloodPurifier"),
    ("Literjon", "Literjon"),
]

SKILL_MODULES = [
    "Swordmaster_T1",
    "BeneGesserit_T1",
    "Trooper_T1",
    "Planetologist_T1",
    "Mentat_T1",
    "Skills.Ability.Hypersprint",
]


def bind(main) -> None:
    global M, CONFIG_FILE, NOTES_FILE, WELCOME_FILE
    M = main
    CONFIG_FILE = M.DUNE / "admin-config.json"
    NOTES_FILE = M.DUNE / "admin-notes.json"
    WELCOME_FILE = M.DUNE / "admin-welcome.json"
    M.steam_ids = steam_ids
    M.host_health = host_health
    M.net_health = net_health
    M.list_backups = list_backups
    M.read_settings = read_settings
    M.write_settings = write_settings
    M.player_detail = player_detail
    M.read_audit = read_audit
    M.read_admin_config = read_admin_config
    M.catalog = catalog
    M.extra_action = extra_action
    M.tick_extras = tick_extras
    M.enrich_players = enrich_players
    M.enrich_status = enrich_status


def cfg() -> dict:
    d = M.load_json_file(CONFIG_FILE, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("webhook_url", "")
    d.setdefault("welcome", {"enabled": False, "items": []})
    d.setdefault("schedule", None)
    d.setdefault("motd", "")
    d.setdefault("waypoints", [])
    return d


def save_cfg(d: dict) -> None:
    M.save_json_file(CONFIG_FILE, d)


def catalog() -> dict:
    return {"items": CATALOG, "skills": SKILL_MODULES}


def _json_get(obj, *path, default=None):
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _pretty_tech(key: str) -> str:
    s = (key or "").strip()
    for prefix in ("RCP_T1_", "RCP_T2_", "RCP_T3_", "RCP_T4_", "RCP_T5_", "RCP_T6_", "RCP_", "DA_GRP_", "BLD_"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    s = s.replace("_Recipe", "").replace("_Patent", "").replace("_", " ")
    return s.strip() or key


def _gas_val(gas: dict, set_name: str, attr: str) -> str:
    cur = _json_get(gas, set_name, attr, "CurrentValue")
    if cur is None:
        return ""
    try:
        return ("%g" % float(cur))
    except (TypeError, ValueError):
        return str(cur)


def _load_json_col(sql: str):
    code, out = M.psql(sql)
    if code != 0 or not out.strip():
        return {}
    line = out.strip().splitlines()[0]
    try:
        val = json.loads(line)
        return val if isinstance(val, dict) else {}
    except json.JSONDecodeError:
        return {}


def enrich_status(payload: dict) -> dict:
    payload["steam"] = steam_ids(refresh=False)
    payload["health"] = host_health()
    payload["net"] = net_health()
    payload["schedule"] = cfg().get("schedule")
    payload["welcome_on"] = bool((cfg().get("welcome") or {}).get("enabled"))
    return payload


def enrich_players(players: list) -> list:
    notes = M.load_json_file(NOTES_FILE, {})
    bans = M.load_json_file(M.BANS_FILE, [])
    by_ban = {}
    now = time.time()
    live_bans = []
    changed = False
    for b in bans if isinstance(bans, list) else []:
        if not isinstance(b, dict):
            continue
        exp = b.get("expires")
        if exp and float(exp) < now:
            changed = True
            continue
        live_bans.append(b)
        by_ban[str(b.get("player_id", "")).upper()] = b
    if changed:
        M.save_json_file(M.BANS_FILE, live_bans)
    for p in players:
        pid = (p.get("player_id") or "")
        n = notes.get(pid) or notes.get(pid.upper()) or {}
        p["note"] = n.get("text", "") if isinstance(n, dict) else str(n or "")
        b = by_ban.get(pid.upper()) or {}
        p["ban_expires"] = b.get("expires")
        p["ban_reason"] = b.get("reason", "")
    return players


def steam_ids(refresh: bool = False) -> dict:
    local = ""
    public = ""
    if MANIFEST.is_file():
        t = MANIFEST.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"buildid"\s+"(\d+)"', t)
        local = m.group(1) if m else ""
    if refresh:
        steamcmd = "/home/dune/.local/bin/steamcmd"
        if not os.path.isfile(steamcmd):
            steamcmd = "/home/dune/Steam/steamcmd.sh"
        M.run(
            [
                steamcmd,
                "+@ShutdownOnFailedCommand",
                "1",
                "+@NoPromptForPassword",
                "1",
                "+login",
                "anonymous",
                "+app_info_update",
                "1",
                "+app_info_print",
                "4754530",
                "+quit",
            ],
            timeout=90,
        )
        # maintain writes last-appinfo; also capture from that file if present
    if APPINFO.is_file():
        t = APPINFO.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"branches"\s*\{\s*"public"\s*\{[^}]*?"buildid"\s+"(\d+)"', t, re.S)
        public = m.group(1) if m else ""
    newer = bool(local and public and public != local and public.isdigit() and local.isdigit() and int(public) > int(local))
    return {"local": local, "public": public, "update_available": newer}


def host_health() -> dict:
    now = time.time()
    if _HEALTH_CACHE["v"] and now - _HEALTH_CACHE["t"] < 12:
        return _HEALTH_CACHE["v"]
    n = M.ns()
    top = {}
    code, out = M.run(["sudo", "kubectl", "top", "pods", "-n", n, "--no-headers"], timeout=15)
    if code == 0:
        for line in out.splitlines():
            p = line.split()
            if len(p) >= 3:
                top[p[0]] = {"cpu": p[1], "mem": p[2]}
    pods = []
    code, out = M.run(["sudo", "kubectl", "get", "pods", "-n", n, "--no-headers"], timeout=15)
    if code == 0:
        for line in out.splitlines():
            p = line.split()
            if len(p) >= 4:
                name = p[0]
                if not any(s in name for s in ("sg-survival", "sg-overmap", "bgd-deploy", "db-dbdepl", "mq-game")):
                    continue
                usage = top.get(name) or {}
                pods.append(
                    {
                        "name": name,
                        "ready": p[1],
                        "phase": p[2],
                        "restarts": p[3],
                        "cpu": usage.get("cpu", ""),
                        "mem": usage.get("mem", ""),
                    }
                )
    disk = ""
    code, out = M.run(["df", "-h", "/"], timeout=8)
    if code == 0:
        rows = out.strip().splitlines()
        if len(rows) >= 2:
            disk = rows[-1]
    mem = ""
    try:
        text = Path("/proc/meminfo").read_text()
        tot = re.search(r"MemTotal:\s+(\d+)", text)
        ava = re.search(r"MemAvailable:\s+(\d+)", text)
        if tot and ava:
            mem = "available %.1f / %.1f GiB" % (int(ava.group(1)) / 1048576, int(tot.group(1)) / 1048576)
    except OSError:
        pass
    reclaim = "unknown"
    if WSLCONFIG.is_file():
        wt = WSLCONFIG.read_text(encoding="utf-8", errors="replace")
        reclaim = "disabled" if re.search(r"(?im)^\s*autoMemoryReclaim\s*=\s*disabled\s*$", wt) else "not-disabled"
    outp = {"pods": pods, "disk": disk, "mem": mem, "wsl_reclaim": reclaim}
    _HEALTH_CACHE["t"] = now
    _HEALTH_CACHE["v"] = outp
    return outp


def net_health() -> dict:
    now = time.time()
    if _NET_CACHE["v"] and now - _NET_CACHE["t"] < 12:
        return _NET_CACHE["v"]
    n = M.ns()
    pod = M.pod_name("sg-survival")
    if not n or not pod:
        return {"error": "no survival pod"}
    _c, logs = M.run(
        ["sudo", "kubectl", "logs", "-n", n, pod, "--since=15m", "--tail=400"],
        timeout=20,
        redact_out=True,
    )
    expired = len(re.findall(r"ServerMove: TimeStamp expired", logs))
    addrs = {}
    for ip in re.findall(r"RemoteAddr:\s*([0-9.]+)", logs):
        addrs[ip] = addrs.get(ip, 0) + 1
    pub = ""
    adv = M.advertise_status()
    m = re.search(r"HOST_DATACENTER=(\S+)", adv)
    if m:
        pub = m.group(1)
    lan = ""
    if M.LAN_FILE.is_file():
        lan = M.LAN_FILE.read_text(encoding="utf-8", errors="replace").strip()
    classified = []
    for ip, c in sorted(addrs.items(), key=lambda kv: -kv[1])[:12]:
        kind = "internet"
        if pub and ip == pub:
            kind = "hairpin-or-self-wan"
        elif re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)", ip):
            kind = "lan"
        classified.append({"ip": ip, "count": c, "kind": kind})
    outp = {"expired_15m": expired, "remotes": classified, "advertise": pub, "lan": lan}
    _NET_CACHE["t"] = now
    _NET_CACHE["v"] = outp
    return outp


def fb_exec(args: list[str], timeout: int = 20) -> tuple[int, str]:
    n = M.ns()
    pod = M.pod_name("fb-deploy")
    if not n or not pod:
        return 1, "no filebrowser pod"
    return M.run(["sudo", "kubectl", "exec", "-n", n, pod, "--", *args], timeout=timeout)


def list_backups() -> list[dict]:
    code, out = fb_exec(
        [
            "sh",
            "-c",
            "for f in /srv/DatabaseDumps/*.backup; do "
            '[ -f "$f" ] || continue; stat -c "%s %Y %n" "$f"; '
            "done",
        ],
        timeout=25,
    )
    rows = []
    if code != 0:
        return rows
    for line in out.splitlines():
        p = line.strip().split(None, 2)
        if len(p) < 3:
            continue
        name = p[2].rsplit("/", 1)[-1]
        try:
            rows.append({"name": name, "bytes": int(p[0]), "mtime": int(p[1])})
        except ValueError:
            continue
    rows.sort(key=lambda r: r.get("mtime") or 0, reverse=True)
    return rows


def ini_get(text: str, key: str) -> str:
    m = re.search(r"(?m)^[;\s]*%s\s*=\s*(.*)$" % re.escape(key), text)
    return m.group(1).strip() if m else ""


def ini_set(text: str, key: str, value: str) -> str:
    line = "%s=%s" % (key, value)
    pat = re.compile(r"(?m)^[;\s]*%s\s*=.*$" % re.escape(key))
    if pat.search(text):
        return pat.sub(line, text, count=1)
    return text.rstrip() + "\n" + line + "\n"


def read_settings() -> dict:
    files = {}
    values = []
    for fname, key in INI_KEYS:
        if fname not in files:
            code, out = fb_exec(["cat", "/srv/UserSettings/" + fname])
            files[fname] = out if code == 0 else ""
            if code != 0 and (SETUP_CFG / fname).is_file():
                files[fname] = (SETUP_CFG / fname).read_text(encoding="utf-8", errors="replace")
        val = ini_get(files[fname], key)
        if key == "m_BaseBackupToolTimeRestrictionInSeconds" and not val:
            val = "604800"
        values.append({"file": fname, "key": key, "value": val})
    return {"keys": values}


def write_settings(updates: list) -> tuple[bool, str]:
    by_file: dict[str, list] = {}
    for u in updates:
        by_file.setdefault(str(u.get("file")), []).append(u)
    msgs = []
    for fname, items in by_file.items():
        if fname not in ("UserServerCustomSettings.ini", "UserGame.ini", "UserEngine.ini"):
            return False, "bad ini name"
        code, text = fb_exec(["cat", "/srv/UserSettings/" + fname])
        if code != 0:
            p = SETUP_CFG / fname
            if not p.is_file():
                return False, "cannot read " + fname
            text = p.read_text(encoding="utf-8", errors="replace")
        for u in items:
            key = str(u.get("key") or "")
            if not any(f == fname and k == key for f, k in INI_KEYS):
                continue
            text = ini_set(text, key, str(u.get("value") or "").strip())
        dest_setup = SETUP_CFG / fname
        dest_setup.parent.mkdir(parents=True, exist_ok=True)
        dest_setup.write_text(text, encoding="utf-8")
        n = M.ns()
        pod = M.pod_name("fb-deploy")
        if not n or not pod:
            return False, "no filebrowser pod"
        p = M.run(
            ["sudo", "kubectl", "exec", "-i", "-n", n, pod, "--", "tee", "/srv/UserSettings/" + fname],
            timeout=20,
            inp=text,
        )
        msgs.append("%s wrote code=%s" % (fname, p[0]))
        if p[0] != 0:
            return False, p[1][:400]
    return True, "\n".join(msgs)


def _psql_rows(sql: str) -> list[list[str]]:
    code, out = M.psql(sql)
    if code != 0 or not out.strip():
        return []
    return [ln.split("\t") for ln in out.splitlines() if ln.strip()]


def player_row(pid: str) -> dict:
    pid = M.normalize_player_id(pid).replace("'", "")
    rows = _psql_rows(
        "SELECT ps.character_name, ps.last_login_time::text, ps.online_status::text, "
        "ps.player_controller_id::text, ps.account_id::text, a.\"user\"::text, "
        "COALESCE(a.funcom_id,''), COALESCE(ps.player_pawn_id::text,''), "
        "COALESCE(f.faction_id::text,''), COALESCE(ps.id::text,''), "
        "COALESCE(ps.life_state::text,''), COALESCE(ps.character_state::text,''), "
        "COALESCE(a.platform_name,'') "
        "FROM dune.player_state ps "
        "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
        "LEFT JOIN dune.player_faction f ON f.actor_id = ps.player_pawn_id "
        "WHERE a.\"user\"::text ILIKE '%s' OR ps.account_id::text = '%s' "
        "LIMIT 1" % (pid, pid)
    )
    if not rows:
        return {}
    r = rows[0]
    return {
        "name": r[0] if len(r) > 0 else "",
        "last_login": r[1] if len(r) > 1 else "",
        "online_status": r[2] if len(r) > 2 else "",
        "controller_id": r[3] if len(r) > 3 else "",
        "account_id": r[4] if len(r) > 4 else "",
        "fls_id": r[5] if len(r) > 5 else pid,
        "funcom_id": r[6] if len(r) > 6 else "",
        "pawn_id": r[7] if len(r) > 7 else "",
        "faction_id": r[8] if len(r) > 8 else "",
        "state_id": r[9] if len(r) > 9 else "",
        "life_state": r[10] if len(r) > 10 else "",
        "character_state": r[11] if len(r) > 11 else "",
        "platform": r[12] if len(r) > 12 else "",
    }


def player_detail(pid: str) -> dict:
    base = player_row(pid)
    if not base:
        loc = M.player_location(pid)
        return {"ok": False, "error": "character not found", "location": loc}
    ctrl = (base.get("controller_id") or "").replace("'", "")
    pawn = (base.get("pawn_id") or "").replace("'", "")
    inventory = []
    if pawn:
        for r in _psql_rows(
            "SELECT i.template_id::text, COALESCE(i.stack_size::text,'1'), "
            "COALESCE(i.quality_level::text,''), COALESCE(inv.inventory_type::text,'') "
            "FROM dune.inventories inv JOIN dune.items i ON i.inventory_id = inv.id "
            "WHERE inv.actor_id::text = '%s' ORDER BY i.position_index LIMIT 250" % pawn
        ):
            inventory.append(
                {"template_id": r[0], "qty": r[1] if len(r) > 1 else "1", "quality": r[2] if len(r) > 2 else "", "inv": r[3] if len(r) > 3 else ""}
            )
    guilds = []
    if ctrl:
        for r in _psql_rows(
            "SELECT g.guild_name, COALESCE(g.guild_faction::text,''), COALESCE(gm.role_id::text,'') "
            "FROM dune.guild_members gm JOIN dune.guilds g ON g.guild_id = gm.guild_id "
            "WHERE gm.player_id::text = '%s'" % ctrl
        ):
            guilds.append({"name": r[0], "faction": r[1] if len(r) > 1 else "", "role": r[2] if len(r) > 2 else ""})
    currency = []
    if ctrl:
        for r in _psql_rows(
            "SELECT currency_id::text, balance::text FROM dune.player_virtual_currency_balances "
            "WHERE player_controller_id::text = '%s'" % ctrl
        ):
            currency.append({"id": r[0], "balance": r[1] if len(r) > 1 else ""})
        for r in _psql_rows(
            "SELECT solari_balance::text FROM dune.dune_exchange_users WHERE owner_id::text = '%s'" % ctrl
        ):
            currency.append({"id": "solari_exchange", "balance": r[0]})
    bases = []
    if ctrl:
        for r in _psql_rows(
            "SELECT id::text, COALESCE(building_blueprint_map::text,''), COALESCE(item_id::text,'') "
            "FROM dune.building_blueprints WHERE player_id::text = '%s' LIMIT 50" % ctrl
        ):
            bases.append({"id": r[0], "map": r[1] if len(r) > 1 else "", "item": r[2] if len(r) > 2 else ""})
        for r in _psql_rows(
            "SELECT id::text, COALESCE(base_backup_name,''), COALESCE(last_edited_by_player_id::text,'') "
            "FROM dune.base_backups WHERE player_id::text = '%s' LIMIT 20" % ctrl
        ):
            bases.append({"id": r[0], "backup": r[1] if len(r) > 1 else "", "item": "backup"})
    landsraad = []
    contrib_key = ctrl or pawn
    if contrib_key:
        for r in _psql_rows(
            "SELECT COALESCE(t.house_name,''), c.amount::text, c.faction_id::text "
            "FROM dune.landsraad_task_player_contributions c "
            "LEFT JOIN dune.landsraad_tasks t ON t.id = c.task_id "
            "WHERE c.player_id::text = '%s' LIMIT 40" % contrib_key
        ):
            landsraad.append({"house": r[0], "amount": r[1] if len(r) > 1 else "", "faction": r[2] if len(r) > 2 else ""})
    totems = []
    loc = M.player_location(pid)
    state_id = (base.get("state_id") or "").replace("'", "")
    tags = []
    if state_id:
        for r in _psql_rows(
            "SELECT DISTINCT tag FROM dune.player_tags WHERE character_id::text = '%s' ORDER BY 1" % state_id
        ):
            if r and r[0]:
                tags.append(r[0])
    mentors = sorted({t.split(".")[-1] for t in tags if t.startswith("DialogueFlags.Mentor.")})
    castes = sorted({t.split(".")[-1] for t in tags if t.startswith("DialogueFlags.Caste.")})
    schools = []
    for t in tags:
        if "Trainer_" in t or t.endswith("T1Complete"):
            name = t.split(".")[-1].replace("Trainer_", "").replace("T1Complete", "").replace("Complete", "")
            name = name.replace("Planetologist1_01", "Planetologist").replace("Trooper1_01A", "Trooper")
            if name and name not in schools:
                schools.append(name)
    schools.sort()
    contracts_done = sum(1 for t in tags if t.startswith("Contract.Tracking.Completed."))
    pois = sorted({t.split(".")[-1] for t in tags if t.startswith("Exploration.POI.")})
    npe_done = any(t == "NPE.HasCompletedNPE" for t in tags)
    tracks = []
    if ctrl:
        for r in _psql_rows(
            "SELECT track_type::text, COALESCE(level::text,''), COALESCE(xp_amount::text,'') "
            "FROM dune.specialization_tracks WHERE player_id::text = '%s' "
            "AND track_type::text IN ('Combat','Gathering','Exploration','Crafting','Sabotage')" % ctrl
        ):
            tracks.append({"track": r[0], "level": r[1] if len(r) > 1 else "", "xp": r[2] if len(r) > 2 else ""})
    reputation = []
    for key in (ctrl, pawn, state_id):
        if not key:
            continue
        for r in _psql_rows(
            "SELECT COALESCE(f.name, r.faction_id::text), r.reputation_amount::text "
            "FROM dune.player_faction_reputation r "
            "LEFT JOIN dune.factions f ON f.id = r.faction_id "
            "WHERE r.actor_id::text = '%s'" % key
        ):
            reputation.append({"faction": r[0], "amount": r[1] if len(r) > 1 else ""})
        if reputation:
            break
    journey = {}
    if ctrl:
        for r in _psql_rows(
            "SELECT COALESCE(tracked_journey_card,''), COALESCE(tracked_landsraad_card,'') "
            "FROM dune.journey_tracked_cards WHERE player_id::text = '%s' LIMIT 1" % ctrl
        ):
            journey = {"journey": r[0], "landsraad": r[1] if len(r) > 1 else ""}
    respawns = []
    if state_id:
        for r in _psql_rows(
            "SELECT COALESCE(locator_name,''), COALESCE(map,'') "
            "FROM dune.player_respawn_locations WHERE character_id::text = '%s' "
            "AND COALESCE(locator_name,'') <> '' "
            "ORDER BY last_used_timestamp DESC NULLS LAST LIMIT 8" % state_id
        ):
            respawns.append({"name": r[0], "map": r[1] if len(r) > 1 else ""})
    pawn_map = ""
    vitals = {}
    tech = {"points": "", "purchased": 0, "pending": 0, "recipes": []}
    if pawn:
        props = _load_json_col(
            "SELECT properties::text FROM dune.actors WHERE id::text = '%s' LIMIT 1" % pawn
        )
        gas = _load_json_col(
            "SELECT gas_attributes::text FROM dune.actors WHERE id::text = '%s' LIMIT 1" % pawn
        )
        for r in _psql_rows(
            "SELECT COALESCE(map,''), COALESCE(transform::text,'') FROM dune.actors WHERE id::text = '%s' LIMIT 1" % pawn
        ):
            pawn_map = r[0]
            if not loc:
                loc = M._parse_xyz(r[1] if len(r) > 1 else "")
        tk = props.get("TechKnowledgePlayerComponent") or {}
        recipes = _json_get(tk, "m_TechKnowledge", "m_TechKnowledgeData") or []
        purchased, pending, shown = [], [], []
        if isinstance(recipes, list):
            for rec in recipes:
                if not isinstance(rec, dict):
                    continue
                key = str(rec.get("ItemKey") or "")
                state = str(rec.get("UnlockedState") or "")
                row = {"key": key, "name": _pretty_tech(key), "state": state}
                if state == "Purchased":
                    purchased.append(row)
                else:
                    pending.append(row)
            shown = purchased[:40] + pending[:10]
        tech = {
            "points": tk.get("m_TechKnowledgePoints", ""),
            "upgrade_index": tk.get("m_NextTechTreeUpgradeIndex", ""),
            "purchased": len(purchased),
            "pending": len(pending),
            "recipes": shown,
        }
        dmg = props.get("DamageableActorComponent") or {}
        bp = props.get("BP_DunePlayerCharacter_C") or {}
        try:
            eyes = float(bp.get("m_EyesOfIbadValue") or 0)
        except (TypeError, ValueError):
            eyes = 0.0
        vitals = {
            "health": dmg.get("m_CurrentMaxHealth", ""),
            "health_max": dmg.get("m_TotalMaxHealth", ""),
            "hydration": _gas_val(gas, "DuneHydrationAttributeSet", "CurrentHydration"),
            "heat": _gas_val(gas, "DuneHydrationAttributeSet", "HeatExhaustion"),
            "spice": _gas_val(gas, "DuneSpiceAddictionAttributeSet", "CurrentSpice"),
            "spice_addiction": _gas_val(gas, "DuneSpiceAddictionAttributeSet", "SpiceAddictionLevel"),
            "heatstroke": bool(bp.get("m_bHeatstroke")),
            "eyes_of_ibad": ("%g" % (eyes * 100.0)) if eyes else "0",
            "driving": bool(bp.get("m_bIsDriving")),
            "map": pawn_map,
        }
        if pawn_map:
            base["map"] = pawn_map
    notes = M.load_json_file(NOTES_FILE, {})
    note = notes.get(pid) or notes.get((base.get("fls_id") or "").upper()) or {}
    return {
        "ok": True,
        "player": base,
        "inventory": inventory,
        "guilds": guilds,
        "currency": currency,
        "bases": bases,
        "landsraad": landsraad,
        "totems": totems,
        "location": loc,
        "note": note.get("text", "") if isinstance(note, dict) else "",
        "mentors": mentors,
        "castes": castes,
        "schools": schools,
        "tracks": tracks,
        "tech": tech,
        "vitals": vitals,
        "journey": journey,
        "reputation": reputation,
        "respawns": respawns,
        "npe_done": npe_done,
        "contracts_done": contracts_done,
        "pois": pois,
    }


def read_audit(limit: int = 80) -> list:
    path = M.AUDIT_FILE
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows.reverse()
    return rows


def read_admin_config() -> dict:
    c = cfg()
    url = str(c.get("webhook_url") or "")
    host = ""
    if url:
        try:
            host = urlparse(url).netloc
        except Exception:
            host = "(set)"
    return {
        "webhook_set": bool(url),
        "webhook_host": host,
        "welcome": c.get("welcome") or {"enabled": False, "items": []},
        "schedule": c.get("schedule"),
    }


def webhook(event: str, text: str) -> None:
    url = str(cfg().get("webhook_url") or "").strip()
    if not url.startswith("http"):
        return
    body = json.dumps({"content": "[%s] %s" % (event, text[:1800])}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "DuneAdmin/1"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        pass


def extra_action(body: dict):
    op = str(body.get("op") or "")
    pid = M.normalize_player_id(str(body.get("player_id") or ""))
    confirm = bool(body.get("confirm"))

    if op == "check-update":
        # Refresh last-appinfo via steamcmd the same way maintain does.
        steamcmd = "/home/dune/.local/bin/steamcmd"
        if not os.path.isfile(steamcmd):
            steamcmd = "/home/dune/Steam/steamcmd.sh"
        code, out = M.run(
            [
                steamcmd,
                "+@ShutdownOnFailedCommand",
                "1",
                "+@NoPromptForPassword",
                "1",
                "+login",
                "anonymous",
                "+app_info_update",
                "1",
                "+app_info_print",
                "4754530",
                "+quit",
            ],
            timeout=120,
        )
        try:
            APPINFO.write_text(out, encoding="utf-8")
        except OSError:
            pass
        ids = steam_ids(refresh=False)
        ids["ok"] = True
        ids["out"] = "steamcmd=%s" % code
        return ids
    if op == "apply-update":
        if not confirm:
            return {"ok": False, "error": "confirm required"}
        log = "/home/dune/.dune/admin-maintain.log"
        subprocess.Popen(
            ["/home/dune/.dune/bin/dune-maintain.sh"],
            stdout=open(log, "ab", buffering=0),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "HOME": "/home/dune"},
        )
        webhook("restart", "Depot maintain started from admin panel")
        return {"ok": True, "out": "maintain started in background; maps roll only if a newer depot is waiting"}
    if op == "restore-backup":
        if str(body.get("confirm_text") or "") != "RESTORE":
            return {"ok": False, "error": 'type RESTORE to import (overwrites the live world)'}
        name = str(body.get("name") or "").strip()
        if not re.match(r"^[\w.\-]+\.backup$", name):
            return {"ok": False, "error": "bad backup name"}
        code, out = M.battlegroup("import", [name])
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "schedule-restart":
        lead = int(body.get("lead") or 600)
        when = int(body.get("at") or 0)
        if when < time.time() + 30:
            return {"ok": False, "error": "pick a time at least 30s in the future"}
        c = cfg()
        c["schedule"] = {"at": when, "lead": lead, "announced": False}
        save_cfg(c)
        return {"ok": True, "out": "scheduled", "schedule": c["schedule"]}
    if op == "cancel-schedule":
        c = cfg()
        c["schedule"] = None
        save_cfg(c)
        ok, msg = M.mq_publish(
            {
                "ServerCommand": "ServiceBroadcast",
                "BroadcastType": "ServerShutdown",
                "ShouldCancel": True,
            }
        )
        return {"ok": True, "out": "cleared; cancel-broadcast " + msg}
    if op == "rotate-token":
        if not confirm:
            return {"ok": False, "error": "confirm required"}
        tok = secrets.token_urlsafe(24)
        M.TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
        os.chmod(M.TOKEN_FILE, 0o600)
        return {"ok": True, "token": tok, "out": "new token — copy it now; old one stops working"}
    if op == "save-note":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        notes = M.load_json_file(NOTES_FILE, {})
        notes[pid] = {"text": str(body.get("note") or "")[:2000], "ts": M._now()}
        M.save_json_file(NOTES_FILE, notes)
        return {"ok": True, "out": "saved"}
    if op == "save-config":
        c = cfg()
        if "webhook_url" in body:
            url = str(body.get("webhook_url") or "").strip()
            if url and not url.startswith("https://"):
                return {"ok": False, "error": "webhook must be https"}
            c["webhook_url"] = url
        if "welcome" in body and isinstance(body.get("welcome"), dict):
            w = body["welcome"]
            items = []
            for it in w.get("items") or []:
                name = str(it.get("item") or "").strip()
                if name:
                    items.append({"item": name, "qty": int(it.get("qty") or 1)})
            c["welcome"] = {"enabled": bool(w.get("enabled")), "items": items[:12]}
        save_cfg(c)
        return {"ok": True, "out": "saved"}
    if op == "save-settings":
        keys = body.get("keys") or []
        if not isinstance(keys, list):
            return {"ok": False, "error": "keys required"}
        ok, msg = write_settings(keys)
        return {"ok": ok, "out": msg}
    if op == "apply-settings":
        if not confirm:
            return {"ok": False, "error": "confirm required (applies INIs; restart maps to take effect)"}
        code, out = M.battlegroup("apply-default-usersettings")
        return {"ok": code == 0, "out": out[-4000:] + "\nRestart the battlegroup for rates to load."}
    if op == "skill-module":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        mod = str(body.get("module") or "").strip()
        if not mod:
            return {"ok": False, "error": "module required"}
        ok, msg = M.mq_publish(
            {
                "ServerCommand": "SkillsSetModuleLevel",
                "PlayerId": pid,
                "Module": mod,
                "Level": int(body.get("level") or 1),
            }
        )
        return {"ok": ok, "out": msg}
    if op == "teleport-to-player":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        dest = M.normalize_player_id(str(body.get("target_id") or ""))
        loc = M.player_location(dest)
        if not loc:
            return {"ok": False, "error": "could not read target location (they may be offline)"}
        ok, msg = M.mq_publish(
            {
                "ServerCommand": "TeleportTo",
                "PlayerId": pid,
                "X": loc["x"],
                "Y": loc["y"],
                "Z": loc["z"],
            }
        )
        return {"ok": ok, "out": msg, "at": loc}
    if op == "welcome-now":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        return grant_welcome(pid, force=True)
    return None


def grant_welcome(pid: str, force: bool = False) -> dict:
    w = cfg().get("welcome") or {}
    items = w.get("items") or []
    if not items:
        return {"ok": False, "error": "welcome kit is empty"}
    ledger = M.load_json_file(WELCOME_FILE, {})
    if not force and ledger.get(pid):
        return {"ok": True, "out": "already granted"}
    msgs = []
    ok_all = True
    for it in items:
        ok, msg = M.mq_publish(
            {
                "ServerCommand": "AddItemToInventory",
                "PlayerId": pid,
                "ItemName": str(it.get("item")),
                "Quantity": int(it.get("qty") or 1),
                "Durability": 1.0,
            }
        )
        ok_all = ok_all and ok
        msgs.append(msg)
    if ok_all or force:
        ledger[pid] = {"ts": M._now()}
        M.save_json_file(WELCOME_FILE, ledger)
    return {"ok": ok_all, "out": "; ".join(msgs)}


def tick_extras() -> None:
    global _LAST_ONLINE, _WAS_JOINABLE, _ONLINE_READY
    try:
        ip = M.lan_ip()
        st = M.world_status(ip)
    except Exception:
        return
    joinable = bool(st.get("joinable"))
    if _WAS_JOINABLE and not joinable:
        webhook("map_down", "World not joinable: " + ", ".join(st.get("join_notes") or []))
    _WAS_JOINABLE = joinable
    players, _e = M.load_players()
    online = {p.get("player_id") for p in players if p.get("online") and p.get("player_id")}
    if _ONLINE_READY:
        for pid in sorted(online - _LAST_ONLINE):
            name = next((p.get("name") for p in players if p.get("player_id") == pid), "")
            webhook("join", "%s %s" % (name or "player", pid[:12]))
            w = cfg().get("welcome") or {}
            if w.get("enabled") and w.get("items"):
                grant_welcome(pid)
        for pid in sorted(_LAST_ONLINE - online):
            webhook("leave", pid[:12])
    _LAST_ONLINE = online
    _ONLINE_READY = True
    sch = cfg().get("schedule")
    if not isinstance(sch, dict):
        return
    at = float(sch.get("at") or 0)
    lead = float(sch.get("lead") or 600)
    now = time.time()
    if at <= 0:
        return
    if not sch.get("announced") and now >= at - lead:
        M.mq_publish(
            {
                "ServerCommand": "ServiceBroadcast",
                "BroadcastType": "ServerShutdown",
                "ShutdownType": "Restart",
                "ShutdownDuration": max(30, int(at - now)),
                "BroadcastFrequency": 60,
                "Title": "Restart",
                "Body": "World restart scheduled from admin panel",
            }
        )
        sch["announced"] = True
        c = cfg()
        c["schedule"] = sch
        save_cfg(c)
        webhook("restart", "Restart countdown started")
    if now >= at:
        webhook("restart", "Restarting battlegroup now")
        M.battlegroup("restart")
        c = cfg()
        c["schedule"] = None
        save_cfg(c)
