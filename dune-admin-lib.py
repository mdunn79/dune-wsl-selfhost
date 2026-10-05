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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

M = None
CONFIG_FILE = NOTES_FILE = WELCOME_FILE = PRESENCE_FILE = None
SETUP_CFG = Path("/home/dune/.dune/download/scripts/setup/config")
MANIFEST = Path("/home/dune/.dune/download/steamapps/appmanifest_4754530.acf")
APPINFO = Path("/home/dune/.dune/last-appinfo.txt")
WSLCONFIG = Path("/mnt/c/Users/mdunn/.wslconfig")
_NET_CACHE = {"t": 0.0, "v": {}}
_HEALTH_CACHE = {"t": 0.0, "v": {}}
_SETTINGS_META_CACHE = {"t": 0.0, "v": {}}
_COL_CACHE: dict[str, set[str]] = {}
_LAST_ONLINE: set = set()
_LAST_NAMES: dict = {}
_MAP_READY: dict = {}
_WAS_JOINABLE = False
_WAS_MODIFYING = False
_ONLINE_READY = False

GM_GATES = {
    "grant-item": "grants",
    "welcome-now": "grants",
    "award-xp": "grants",
    "skill-points": "grants",
    "skill-module": "grants",
    "refill-water": "grants",
    "clean-inventory": "wipe_inventory",
    "reset-progression": "reset_progression",
    "teleport": "teleport",
    "teleport-to-player": "teleport",
    "spawn-vehicle": "spawn_vehicle",
}
GM_PHRASES = {
    "clean-inventory": "WIPE",
    "reset-progression": "RESET",
}
LIVE_EFFECT_OPS = set(GM_GATES) | {
    "start",
    "stop",
    "restart",
    "apply-update",
    "apply-settings",
    "restore-backup",
    "advertise-auto",
    "advertise-lan",
    "schedule-restart",
    "kick",
    "ban",
    "broadcast",
    "whitelist-enable",
}

def _k(file: str, key: str, cat: str, hint: str = "") -> dict:
    return {"file": file, "key": key, "cat": cat, "hint": hint}


INI_KEYS = [
    _k("UserServerCustomSettings.ini", "DifficultyLevel", "Custom difficulty", "Must stay Custom or Funcom ignores this file"),
    _k("UserServerCustomSettings.ini", "PVPMode", "PvP", "NoPVP / Limited / FullPVP"),
    _k("UserGame.ini", "m_bShouldForceEnablePvpOnAllPartitions", "PvP", "True forces PvP on every partition"),
    _k("UserGame.ini", "m_bAreSecurityZonesEnabled", "PvP", "False allows PvP/abilities everywhere"),
    _k("UserServerCustomSettings.ini", "PlayerDamageToPlayer", "PvP", "0 to 10; 0 = no player damage"),
    _k("UserServerCustomSettings.ini", "PVPDamageStructures", "PvP", "0 to 10; 0 = structures take no PvP damage"),
    _k("UserEngine.ini", "SecurityZones.PvpResourceMultiplier", "PvP", "Extra yield inside PvP zones"),
    _k("UserServerCustomSettings.ini", "GatheringAmount", "Harvesting", "Duplicates mining CVars; 0.1 to 10"),
    _k("UserEngine.ini", "Dune.GlobalMiningOutputMultiplier", "Harvesting", "Hand mining yield"),
    _k("UserEngine.ini", "Dune.GlobalVehicleMiningOutputMultiplier", "Harvesting", "Vehicle mining yield"),
    _k("UserServerCustomSettings.ini", "CraftingCost", "Harvesting", "0 to 10; 0 = free crafts"),
    _k("UserServerCustomSettings.ini", "CraftingTimeMultiplier", "Harvesting", "0 to 5; 0 = instant"),
    _k("UserServerCustomSettings.ini", "WaterExtractionRate", "Harvesting", "Higher = slower extraction"),
    _k("UserServerCustomSettings.ini", "LootRespawnSpeed", "Harvesting", "Higher = chests take longer"),
    _k("UserServerCustomSettings.ini", "ResourceRespawnSpeed", "Harvesting", "Higher = nodes return sooner"),
    _k("UserServerCustomSettings.ini", "BuildingCostMultiplier", "Harvesting", "0 to 10; 0 = free building"),
    _k("UserServerCustomSettings.ini", "FuelBurnTimeMultiplier", "Harvesting", "0 to 10; 0 = no fuel burn"),
    _k("UserServerCustomSettings.ini", "InventoryVolumeMultiplier", "Harvesting", "Carry volume; 0.1 to 10"),
    _k("UserServerCustomSettings.ini", "PlayerDamageToNPC", "Combat", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "PlayerDamageToVehicle", "Combat", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "NPCHealth", "Combat", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "NPCDamageToPlayer", "Combat", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "NPCDamageToNPC", "Combat", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "NPCRespawnMultiplier", "Combat", "Higher = NPCs return sooner"),
    _k("UserServerCustomSettings.ini", "PlayerStaminaDrain", "Combat", "Higher = stamina drains faster"),
    _k("UserServerCustomSettings.ini", "PlayerShieldDamageAbsorptionMultiplier", "Combat", "Higher = player shields last longer"),
    _k("UserServerCustomSettings.ini", "NPCShieldDamageAbsorptionMultiplier", "Combat", "Higher = NPC shields last longer"),
    _k("UserServerCustomSettings.ini", "GlobalXpMultiplier", "Combat", "0 to 10; 0 = no XP"),
    _k("UserServerCustomSettings.ini", "CombatXp", "Combat", "0 to 10"),
    _k("UserServerCustomSettings.ini", "GatheringXp", "Combat", "0 to 10"),
    _k("UserServerCustomSettings.ini", "MissionXp", "Combat", "0 to 10"),
    _k("UserServerCustomSettings.ini", "IntelPointsGainMultiplier", "Combat", "0 to 10; 0 = no Intel"),
    _k("UserServerCustomSettings.ini", "ItemDurabilityDrainMultiplier", "Durability", "How fast current durability wears; 0 = never wears. Does not change the repair tax."),
    _k("UserServerCustomSettings.ini", "bEnableItemMaxDurabilityLoss", "Durability", "True = repairing cuts max durability (the red bar)"),
    _k("UserEngine.ini", "dw.VehicleDurabilityDamageMultiplier", "Durability", "Vehicle wear; 0 to 10; 0 = off"),
    _k("UserGame.ini", "UpdateRateInSeconds", "Durability", "Item deterioration tick; 0 = off"),
    _k("UserServerCustomSettings.ini", "HeatBuildupRate", "Survival", "0 to 10; 0 = no heat"),
    _k("UserServerCustomSettings.ini", "ThirstMultiplier", "Survival", "0 to 10; 0 = no thirst"),
    _k("UserServerCustomSettings.ini", "DropEquipmentOnDeath", "Survival", "All / Backpack / Default / None"),
    _k("UserServerCustomSettings.ini", "PlayerDeathLootRule", "Survival", "DependsOnSecurityZone / NeverAllowOtherPlayers / AlwaysAllowOtherPlayers"),
    _k("UserServerCustomSettings.ini", "SandwormConsequences", "Survival", "All / Backpack / Default / None"),
    _k("UserServerCustomSettings.ini", "bAllowDynamicBuildingDamage", "Survival", "Storms/decay damage buildings"),
    _k("UserGame.ini", "m_bCoriolisAutoSpawnEnabled", "Storms & worm", "Coriolis auto-spawn"),
    _k("UserEngine.ini", "Sandstorm.Enabled", "Storms & worm", "1 / 0"),
    _k("UserEngine.ini", "Sandstorm.Treasure.Enabled", "Storms & worm", "1 / 0"),
    _k("UserEngine.ini", "sandworm.dune.Enabled", "Storms & worm", "1 / 0"),
    _k("UserEngine.ini", "Sandworm.SandwormDangerZonesEnabled", "Storms & worm", "true / false"),
    _k("UserEngine.ini", "Vehicle.SandwormCollisionInteraction", "Storms & worm", "Worm can shove vehicles"),
    _k("UserEngine.ini", "Vehicle.SandwormInvulnerabilitySecondsOnExit", "Storms & worm", "Seconds after exiting a vehicle"),
    _k("UserEngine.ini", "Vehicle.SandwormInvulnerabilitySecondsOnServerRestart", "Storms & worm", "Seconds after a map restart"),
    _k("UserGame.ini", "HarvestSpicePickupThreatUnit", "Sandworm threat", "Higher = worm breaches sooner"),
    _k("UserGame.ini", "HarvestSpiceCoalesceThreatUnit", "Sandworm threat", ""),
    _k("UserGame.ini", "HarvestFlourSandPickupThreatUnit", "Sandworm threat", ""),
    _k("UserGame.ini", "HarvestFlourSandCoalesceThreatUnit", "Sandworm threat", ""),
    _k("UserGame.ini", "WalkingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "CrouchingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "RunningThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "SprintingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "HyperSprintingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "DashingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "SuspendingThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "DrumsandThreatPerSec", "Sandworm threat", ""),
    _k("UserGame.ini", "ShieldingThreatPerSec", "Sandworm threat", ""),
    _k("UserServerCustomSettings.ini", "LandsraadContributionMultiplier", "Landsraad", "0 to 10"),
    _k("UserServerCustomSettings.ini", "LandsraadSpecializationXpMultiplier", "Landsraad", "0 to 10"),
    _k("UserServerCustomSettings.ini", "LandsraadFactionStandingMultiplier", "Landsraad", "0 to 10"),
    _k("UserServerCustomSettings.ini", "bLandsraadDisableDecreeRerollLimit", "Landsraad", "True / False"),
    _k("UserGame.ini", "m_MaxNumLandclaimSegments", "Building", "Also needed on each client"),
    _k("UserGame.ini", "m_BuildingBlueprintMaxExtensions", "Building", "Landclaim expansions"),
    _k("UserGame.ini", "m_BaseBackupMaxExtensions", "Building", ""),
    _k("UserGame.ini", "m_bBuildingRestrictionLimitsEnabled", "Building", "Also needed on each client"),
    _k("UserGame.ini", "m_BaseBackupToolTimeRestrictionInSeconds", "Building", "604800 = 7 days; UserGame seconds"),
    _k("UserServerCustomSettings.ini", "BaseBackupToolTimeRestriction", "Building", "Hours; custom-settings copy of the cooldown"),
    _k("UserServerCustomSettings.ini", "BuildingPieceLimitMultiplier", "Building", "0.1 to 10"),
    _k("UserServerCustomSettings.ini", "bBuildingInfiniteStability", "Building", "True / False"),
    _k("UserEngine.ini", "Bgd.ServerDisplayName", "Listing", "Sietch name in Funcom directory"),
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
    ("Calibrated servok", "T3MiningGalleryComponent1"),
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
    global M, CONFIG_FILE, NOTES_FILE, WELCOME_FILE, PRESENCE_FILE
    M = main
    CONFIG_FILE = M.DUNE / "admin-config.json"
    NOTES_FILE = M.DUNE / "admin-notes.json"
    WELCOME_FILE = M.DUNE / "admin-welcome.json"
    PRESENCE_FILE = M.DUNE / "admin-presence.json"
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
    M.prepare_gm = prepare_gm
    M.finish_gm = finish_gm
    M.stamp_op = stamp_op
    M.world_objects = world_objects
    M.social_intel = social_intel


def cfg() -> dict:
    d = M.load_json_file(CONFIG_FILE, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("webhook_url", "")
    d.setdefault("welcome", {"enabled": False, "items": []})
    d.setdefault("schedule", None)
    d.setdefault("motd", "")
    d.setdefault("waypoints", [])
    d.setdefault(
        "gates",
        {
            "grants": True,
            "wipe_inventory": True,
            "reset_progression": True,
            "teleport": True,
            "spawn_vehicle": True,
        },
    )
    d.setdefault(
        "presence",
        {
            "discord_join": True,
            "discord_leave": True,
            "discord_maps": True,
            "restart_defer_if_online": True,
        },
    )
    return d


def save_cfg(d: dict) -> None:
    M.save_json_file(CONFIG_FILE, d)


def presence_cfg() -> dict:
    return cfg().get("presence") or {}


def load_presence_store() -> dict:
    d = M.load_json_file(PRESENCE_FILE, {})
    if not isinstance(d, dict):
        d = {}
    fs = d.get("first_seen")
    if not isinstance(fs, dict):
        d["first_seen"] = {}
    return d


def restart_deferred_reason(online_n: int | None = None) -> str:
    if not presence_cfg().get("restart_defer_if_online", True):
        return ""
    if online_n is None:
        players, _e = M.load_players()
        online_n = sum(1 for p in players if p.get("online") and p.get("player_id"))
    if online_n:
        return "restart deferred: %d player(s) online (Settings → defer if anyone is online)" % online_n
    return ""


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


def battlegroup_overview() -> dict:
    n = M.ns()
    out = {
        "phase": "",
        "server_group_phase": "",
        "gateway_phase": "",
        "modifying": False,
        "servers": [],
    }
    if not n:
        return out
    data = M.kubectl_json(["get", "battlegroup", "-n", n])
    if not isinstance(data, dict):
        return out
    items = data.get("items") or ([data] if data.get("kind") else [])
    if not items:
        return out
    st = items[0].get("status") or {}
    out["phase"] = str(st.get("phase") or "")
    out["server_group_phase"] = str(st.get("serverGroupPhase") or "")
    gw = (st.get("utilities") or {}).get("serverGateway") if isinstance(st.get("utilities"), dict) else {}
    if isinstance(gw, dict):
        out["gateway_phase"] = str(gw.get("phase") or "")
    servers = st.get("servers") if isinstance(st.get("servers"), list) else []
    for s in servers:
        if not isinstance(s, dict):
            continue
        rec = {
            "map": str(s.get("partitionMap") or ""),
            "phase": str(s.get("phase") or ""),
            "ready": bool(s.get("ready")),
            "restarts": s.get("restarts") or 0,
        }
        out["servers"].append(rec)
        blob = (rec["phase"] + " " + rec["map"]).lower()
        if "modif" in blob:
            out["modifying"] = True
    for extra in (out["phase"], out["server_group_phase"], out["gateway_phase"]):
        if "modif" in extra.lower():
            out["modifying"] = True
    return out


def overview_map() -> dict:
    """Pawn XY plus overmap dots. SELECT only."""
    hid = (M.world_host_id() or "").replace("'", "")
    user_sql = (
        "CASE WHEN upper(acc.\"user\"::text) = '%s' THEN acc.funcom_id::text ELSE "
        "COALESCE(NULLIF(acc.\"user\"::text,''), acc.funcom_id::text, '') END" % hid
        if hid
        else 'COALESCE(NULLIF(acc."user"::text,\'\'), acc.funcom_id::text, \'\')'
    )
    dots = []
    for r in _psql_rows(
        "SELECT COALESCE(ps.character_name,''), %s, "
        "LOWER(COALESCE(ps.online_status::text,'')), act.transform::text, "
        "COALESCE(act.map,'') "
        "FROM dune.player_state ps "
        "JOIN dune.actors act ON act.id = ps.player_pawn_id "
        "LEFT JOIN dune.accounts acc ON acc.id = ps.account_id "
        "WHERE act.transform IS NOT NULL LIMIT 200" % user_sql
    ):
        loc = M._parse_xyz(r[3] if len(r) > 3 else "")
        if not loc:
            continue
        mmap = (r[4] if len(r) > 4 else "") or "Hagga"
        dots.append(
            {
                "name": r[0] if r else "",
                "player_id": r[1] if len(r) > 1 else "",
                "online": (r[2] if len(r) > 2 else "") in ("online", "1", "t", "true"),
                "x": loc["x"],
                "y": loc["y"],
                "z": loc["z"],
                "map": mmap,
                "source": "pawn",
            }
        )
    for r in _psql_rows(
        "SELECT COALESCE(ps.character_name,''), COALESCE(op.player_id::text,''), "
        "op.overmap_location::text "
        "FROM dune.overmap_players op "
        "LEFT JOIN dune.player_state ps ON ps.player_controller_id::text = op.player_id::text "
        "LIMIT 50"
    ):
        loc = M._parse_xyz(r[2] if len(r) > 2 else "")
        if not loc:
            continue
        dots.append(
            {
                "name": r[0] if r else "",
                "player_id": r[1] if len(r) > 1 else "",
                "online": True,
                "x": loc["x"],
                "y": loc["y"],
                "z": loc["z"],
                "map": "Overmap",
                "source": "overmap",
            }
        )
    return {"dots": dots, "count": len(dots)}


def social_intel() -> dict:
    """Read-only CHOAM / guilds / Landsraad / Solari. SELECT only."""
    guilds = []
    for r in _psql_rows(
        "SELECT g.guild_id::text, COALESCE(g.guild_name,''), COALESCE(g.guild_faction::text,''), "
        "COALESCE(g.guild_description,''), COUNT(m.player_id)::text "
        "FROM dune.guilds g LEFT JOIN dune.guild_members m ON m.guild_id = g.guild_id "
        "GROUP BY g.guild_id, g.guild_name, g.guild_faction, g.guild_description "
        "ORDER BY g.guild_name LIMIT 50"
    ):
        guilds.append(
            {
                "id": r[0],
                "name": r[1] if len(r) > 1 else "",
                "faction": r[2] if len(r) > 2 else "",
                "description": r[3] if len(r) > 3 else "",
                "members": r[4] if len(r) > 4 else "0",
            }
        )
    members = []
    for r in _psql_rows(
        "SELECT COALESCE(g.guild_name,''), COALESCE(ps.character_name, m.player_id::text), "
        "COALESCE(m.role_id::text,'') "
        "FROM dune.guild_members m "
        "JOIN dune.guilds g ON g.guild_id = m.guild_id "
        "LEFT JOIN dune.player_state ps ON ps.player_controller_id = m.player_id "
        "ORDER BY 1, 2 LIMIT 200"
    ):
        members.append({"guild": r[0], "name": r[1] if len(r) > 1 else "", "role": r[2] if len(r) > 2 else ""})
    invites = []
    icols = table_cols("guild_invites")
    igid = _ident(_first_col(icols, ("guild_id",)))
    ipid = _ident(_first_col(icols, ("player_id", "invitee_id", "invited_player_id")))
    isid = _ident(_first_col(icols, ("sender_player_id", "inviter_id", "sender_id")))
    if igid and ipid:
        from_sql = ("COALESCE(sp.character_name, i.%s::text)" % isid) if isid else "''"
        sender_join = (
            "LEFT JOIN dune.player_state sp ON sp.player_controller_id = i.%s" % isid if isid else ""
        )
        for r in _psql_rows(
            "SELECT COALESCE(g.guild_name,''), COALESCE(ps.character_name, i.%s::text), %s "
            "FROM dune.guild_invites i "
            "LEFT JOIN dune.guilds g ON g.guild_id = i.%s "
            "LEFT JOIN dune.player_state ps ON ps.player_controller_id = i.%s "
            "%s LIMIT 50" % (ipid, from_sql, igid, ipid, sender_join)
        ):
            invites.append({"guild": r[0], "player": r[1] if len(r) > 1 else "", "from": r[2] if len(r) > 2 else ""})
    listings = []
    for r in _psql_rows(
        "SELECT COALESCE(o.template_id,''), COALESCE(o.item_price::text,''), "
        "CASE WHEN o.is_npc_order THEN 'npc' ELSE 'player' END, "
        "COALESCE(ps.character_name, o.owner_id::text), COALESCE(o.expiration_time::text,''), "
        "COALESCE(x.exchange_name,'') "
        "FROM dune.dune_exchange_orders o "
        "LEFT JOIN dune.player_state ps ON ps.player_controller_id = o.owner_id "
        "LEFT JOIN dune.dune_exchanges x ON x.id = o.exchange_id "
        "ORDER BY o.id DESC LIMIT 200"
    ):
        listings.append(
            {
                "item": r[0],
                "price": r[1] if len(r) > 1 else "",
                "seller_kind": r[2] if len(r) > 2 else "",
                "seller": r[3] if len(r) > 3 else "",
                "expires": r[4] if len(r) > 4 else "",
                "exchange": r[5] if len(r) > 5 else "",
            }
        )
    exchanges = []
    for r in _psql_rows("SELECT id::text, COALESCE(exchange_name,'') FROM dune.dune_exchanges ORDER BY id"):
        exchanges.append({"id": r[0], "name": r[1] if len(r) > 1 else ""})
    terms = []
    tcols = table_cols("landsraad_decree_term")
    tidc = _ident(_first_col(tcols, ("term_id", "id")))
    startc = _ident(_first_col(tcols, ("start_time", "start", "begins_at")))
    endc = _ident(_first_col(tcols, ("end_time", "end", "expires_at")))
    reignc = _ident(_first_col(tcols, ("reigning_faction_id", "reigning_faction")))
    actc = _ident(_first_col(tcols, ("active_decree_id", "active_decree")))
    winc = _ident(_first_col(tcols, ("winning_faction_id", "winning_faction")))
    elc = _ident(_first_col(tcols, ("elected_decree_id", "elected_decree")))
    if tidc and startc:
        for r in _psql_rows(
            "SELECT %s::text, COALESCE(%s::text,''), COALESCE(%s::text,''), "
            "COALESCE(%s::text,''), COALESCE(%s::text,''), COALESCE(%s::text,''), COALESCE(%s::text,'') "
            "FROM dune.landsraad_decree_term ORDER BY %s DESC LIMIT 4"
            % (
                tidc,
                startc or "NULL",
                endc or "NULL",
                reignc or "NULL",
                actc or "NULL",
                winc or "NULL",
                elc or "NULL",
                startc,
            )
        ):
            terms.append(
                {
                    "id": r[0],
                    "start": r[1] if len(r) > 1 else "",
                    "end": r[2] if len(r) > 2 else "",
                    "reigning": r[3] if len(r) > 3 else "",
                    "active_decree": r[4] if len(r) > 4 else "",
                    "winning": r[5] if len(r) > 5 else "",
                    "elected_decree": r[6] if len(r) > 6 else "",
                }
            )
    decrees = []
    for r in _psql_rows(
        "SELECT id::text, COALESCE(decree_name,''), CASE WHEN disabled THEN 'off' ELSE 'on' END "
        "FROM dune.landsraad_decrees ORDER BY id LIMIT 40"
    ):
        decrees.append({"id": r[0], "name": r[1] if len(r) > 1 else "", "enabled": r[2] if len(r) > 2 else ""})
    tasks = []
    term_id = terms[0]["id"] if terms else ""
    if term_id:
        for r in _psql_rows(
            "SELECT COALESCE(house_name,''), COALESCE(goal_amount::text,''), "
            "CASE WHEN completed THEN 'done' ELSE 'open' END, COALESCE(winning_faction_id::text,'') "
            "FROM dune.landsraad_tasks WHERE term_id::text = '%s' ORDER BY board_index LIMIT 40"
            % term_id.replace("'", "")
        ):
            tasks.append(
                {
                    "house": r[0],
                    "goal": r[1] if len(r) > 1 else "",
                    "state": r[2] if len(r) > 2 else "",
                    "winning": r[3] if len(r) > 3 else "",
                }
            )
    solari = {}
    for r in _psql_rows(
        "SELECT COALESCE(ps.character_name,'(pawn)'), COALESCE(SUM(i.stack_size),0)::text "
        "FROM dune.items i "
        "JOIN dune.inventories inv ON inv.id = i.inventory_id "
        "JOIN dune.player_state ps ON ps.player_pawn_id = inv.actor_id "
        "WHERE i.template_id = 'SolarisCoin' "
        "GROUP BY 1 LIMIT 80"
    ):
        rec = solari.setdefault(r[0], {"name": r[0], "carried": "0", "bank": "0"})
        rec["carried"] = r[1] if len(r) > 1 else "0"
    ucols = table_cols("dune_exchange_users")
    ownc = _ident(_first_col(ucols, ("owner_id", "player_id", "user_id")))
    balc = _ident(_first_col(ucols, ("solari_balance", "solari", "balance", "currency_balance", "amount")))
    if ownc and balc:
        join_on = "ps.player_controller_id" if "player_controller_id" in table_cols("player_state") else "ps.id"
        for r in _psql_rows(
            "SELECT COALESCE(ps.character_name, u.%s::text), COALESCE(u.%s::text,'0') "
            "FROM dune.dune_exchange_users u "
            "LEFT JOIN dune.player_state ps ON %s = u.%s "
            "LIMIT 80" % (ownc, balc, join_on, ownc)
        ):
            rec = solari.setdefault(r[0], {"name": r[0], "carried": "0", "bank": "0"})
            rec["bank"] = r[1] if len(r) > 1 else "0"
    return {
        "ok": True,
        "guilds": guilds,
        "members": members,
        "invites": invites,
        "listings": listings,
        "exchanges": exchanges,
        "landsraad_terms": terms,
        "decrees": decrees,
        "tasks": tasks,
        "solari": list(solari.values()),
        "listing_count": len(listings),
    }


def enrich_status(payload: dict) -> dict:
    payload["steam"] = steam_ids(refresh=False)
    payload["health"] = host_health()
    payload["net"] = net_health()
    payload["schedule"] = cfg().get("schedule")
    payload["welcome_on"] = bool((cfg().get("welcome") or {}).get("enabled"))
    payload["settings_meta"] = settings_meta()
    payload["presence"] = cfg().get("presence") or {}
    payload["battlegroup"] = battlegroup_overview()
    payload["overview"] = overview_map()
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
    firsts = (load_presence_store().get("first_seen") or {})
    for p in players:
        pid = (p.get("player_id") or "")
        n = notes.get(pid) or notes.get(pid.upper()) or {}
        p["note"] = n.get("text", "") if isinstance(n, dict) else str(n or "")
        b = by_ban.get(pid.upper()) or {}
        p["ban_expires"] = b.get("expires")
        p["ban_reason"] = b.get("reason", "")
        fs = firsts.get(pid) or firsts.get(pid.upper()) or {}
        p["first_seen"] = fs.get("ts") if isinstance(fs, dict) else ""
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
    checked = APPINFO.stat().st_mtime if APPINFO.is_file() else 0
    installed = MANIFEST.stat().st_mtime if MANIFEST.is_file() else 0
    return {
        "local": local,
        "public": public,
        "update_available": newer,
        "checked_ts": checked,
        "installed_ts": installed,
    }


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


def _unreal_log_ts(line: str) -> float | None:
    m = re.search(r"\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})", line or "")
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def net_health() -> dict:
    now = time.time()
    if _NET_CACHE["v"] and now - _NET_CACHE["t"] < 12:
        return _NET_CACHE["v"]
    n = M.ns()
    pod = M.pod_name("sg-survival")
    if not n or not pod:
        return {"error": "no survival pod"}
    _c, logs = M.run(
        ["sudo", "kubectl", "logs", "-n", n, pod, "--since=2h", "--tail=3000"],
        timeout=20,
        redact_out=True,
    )
    cutoff = now - 900
    expired = 0
    addrs = {}
    for ln in logs.splitlines():
        ts = _unreal_log_ts(ln)
        if "ServerMove: TimeStamp expired" in ln and (ts is None or ts >= cutoff):
            expired += 1
        for ip in re.findall(r"RemoteAddr:\s*([0-9.]+)", ln):
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
    outp = {
        "expired_15m": expired,
        "remotes": classified,
        "advertise": pub,
        "lan": lan,
        "remote_window": "2h",
        "remote_note": "Survival LogNet RemoteAddr (connect/error lines, up to 2h). Not a live client list.",
    }
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


def _ini_pair(fname: str) -> tuple[str, str, bool]:
    code, out = fb_exec(["cat", "/srv/UserSettings/" + fname])
    live = out if code == 0 else ""
    fb_ok = code == 0
    setup = ""
    p = SETUP_CFG / fname
    if p.is_file():
        setup = p.read_text(encoding="utf-8", errors="replace")
    if not fb_ok:
        live = setup
    return live, setup, fb_ok


def read_settings() -> dict:
    files: dict[str, tuple[str, str, bool]] = {}
    values = []
    drift_n = 0
    for spec in INI_KEYS:
        fname, key = spec["file"], spec["key"]
        if fname not in files:
            files[fname] = _ini_pair(fname)
        live_text, setup_text, fb_ok = files[fname]
        live_val = ini_get(live_text, key)
        setup_val = ini_get(setup_text, key)
        val = live_val or setup_val
        if key == "m_BaseBackupToolTimeRestrictionInSeconds" and not val:
            val = "604800"
        drift = bool(fb_ok) and live_val != setup_val
        if drift:
            drift_n += 1
        values.append(
            {
                "file": fname,
                "key": key,
                "value": val,
                "setup_value": setup_val,
                "drift": drift,
                "cat": spec["cat"],
                "hint": spec.get("hint") or "",
            }
        )
    meta = settings_meta(values=values, drift_count=drift_n)
    return {"keys": values, **meta}


def settings_meta(values: list | None = None, drift_count: int | None = None) -> dict:
    now = time.time()
    c = cfg()
    apply_ts = c.get("last_apply_ts")
    restart_ts = c.get("last_restart_ts")
    needs = False
    if apply_ts:
        try:
            needs = (not restart_ts) or float(apply_ts) > float(restart_ts)
        except (TypeError, ValueError):
            needs = True
    if values is None:
        cached = _SETTINGS_META_CACHE["v"] or {}
        return {
            "drift_count": cached.get("drift_count") or 0,
            "drift_keys": cached.get("drift_keys") or [],
            "last_apply_ts": apply_ts,
            "last_restart_ts": restart_ts,
            "maps_need_restart": needs,
            "gates": c.get("gates") or {},
        }
    drifted = [k for k in (values or []) if k.get("drift")]
    n = drift_count if drift_count is not None else len(drifted)
    out = {
        "drift_count": n,
        "drift_keys": ["%s:%s" % (k.get("file"), k.get("key")) for k in drifted[:12]],
        "last_apply_ts": apply_ts,
        "last_restart_ts": restart_ts,
        "maps_need_restart": needs,
        "gates": c.get("gates") or {},
    }
    _SETTINGS_META_CACHE["t"] = now
    _SETTINGS_META_CACHE["v"] = out
    return out


def write_settings(updates: list) -> tuple[bool, str]:
    allowed = {(s["file"], s["key"]) for s in INI_KEYS}
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
            if (fname, key) not in allowed:
                continue
            val = str(u.get("value") or "").strip()
            if not val and not ini_get(text, key):
                continue
            text = ini_set(text, key, val)
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


def _ident(name: str) -> str:
    return name if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or "") else ""


def table_cols(table: str) -> set[str]:
    t = _ident(table)
    if not t:
        return set()
    if t not in _COL_CACHE:
        rows = _psql_rows(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='dune' AND table_name='%s'" % t
        )
        _COL_CACHE[t] = {r[0] for r in rows if r}
    return _COL_CACHE[t]


def _first_col(cols: set[str], names: tuple[str, ...]) -> str:
    for n in names:
        if n in cols:
            return n
    return ""


def prepare_gm(body: dict):
    op = str(body.get("op") or "")
    dry = bool(body.get("dry_run"))
    pid = M.normalize_player_id(str(body.get("player_id") or ""))
    gates = cfg().get("gates") or {}
    gate = GM_GATES.get(op)
    if gate and not gates.get(gate, True):
        return {"ok": False, "error": "gate %s is off (Settings)" % gate, "dry_run": dry}
    phrase = GM_PHRASES.get(op)
    if phrase and str(body.get("confirm_text") or "").strip() != phrase:
        return {"ok": False, "error": "type %s to confirm" % phrase, "dry_run": dry}
    if dry and op in LIVE_EFFECT_OPS:
        preview = {
            "ok": True,
            "dry_run": True,
            "op": op,
            "out": "dry-run: %s was not sent to the world" % op,
        }
        if pid:
            preview["player"] = player_row(pid) or {"player_id": pid}
        return preview
    if op == "restart":
        deferred = restart_deferred_reason()
        if deferred:
            return {"ok": False, "error": deferred, "dry_run": dry}
    return None


def finish_gm(body: dict, result: dict) -> dict:
    if not isinstance(result, dict):
        return result
    result.setdefault("dry_run", bool(body.get("dry_run")))
    pid = M.normalize_player_id(str(body.get("player_id") or ""))
    op = str(body.get("op") or "")
    if pid and op in GM_GATES and not body.get("dry_run"):
        try:
            result["player"] = player_detail(pid)
        except Exception:
            result["player"] = player_row(pid)
    return result


def stamp_op(op: str, ok: bool) -> None:
    if not ok:
        return
    now = time.time()
    if op == "apply-settings":
        c = cfg()
        c["last_apply_ts"] = now
        save_cfg(c)
        _SETTINGS_META_CACHE["t"] = 0.0
    elif op == "restart":
        c = cfg()
        c["last_restart_ts"] = now
        save_cfg(c)
        _SETTINGS_META_CACHE["t"] = 0.0


def _short_class(cls: str) -> str:
    s = (cls or "").rsplit("/", 1)[-1]
    return s.replace("_C", "").replace("BP_", "").replace("##", "")


def _owner_index() -> dict:
    rows = _psql_rows(
        'SELECT COALESCE(ps.player_controller_id::text,\'\'), COALESCE(a."user"::text,\'\'), '
        "COALESCE(ps.character_name,''), COALESCE(ps.last_avatar_activity::text,''), "
        "COALESCE(ps.character_state::text,''), COALESCE(ps.transfer_count::text,'0'), "
        "COALESCE(ps.account_id::text,''), COALESCE(ps.player_pawn_id::text,''), "
        "COALESCE(ps.id::text,''), COALESCE(ps.player_state_id::text,'') "
        "FROM dune.player_state ps LEFT JOIN dune.accounts a ON a.id = ps.account_id"
    )
    idx = {"controller": {}, "account": {}, "pawn": {}, "state": {}, "fls": {}}
    for r in rows:
        rec = {
            "controller_id": r[0] if len(r) > 0 else "",
            "player_id": r[1] if len(r) > 1 else "",
            "name": r[2] if len(r) > 2 else "",
            "last_seen": r[3] if len(r) > 3 else "",
            "character_state": r[4] if len(r) > 4 else "",
            "transfer_count": r[5] if len(r) > 5 else "0",
            "account_id": r[6] if len(r) > 6 else "",
            "pawn_id": r[7] if len(r) > 7 else "",
            "state_id": r[8] if len(r) > 8 else "",
        }
        rec["transferred"] = rec["transfer_count"] not in ("", "0")
        if rec["controller_id"]:
            idx["controller"][rec["controller_id"]] = rec
        if rec["account_id"]:
            idx["account"][rec["account_id"]] = rec
        if rec["pawn_id"]:
            idx["pawn"][rec["pawn_id"]] = rec
        if rec["state_id"]:
            idx["state"][rec["state_id"]] = rec
        extra_state = r[9] if len(r) > 9 else ""
        if extra_state:
            idx["state"].setdefault(extra_state, rec)
        if rec["player_id"]:
            idx["fls"][rec["player_id"].upper()] = rec
    return idx


def _lookup_owner(idx: dict, raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw or raw in ("0", "None", "(null)"):
        return {}
    return (
        idx["controller"].get(raw)
        or idx["state"].get(raw)
        or idx["account"].get(raw)
        or idx["pawn"].get(raw)
        or idx["fls"].get(raw.upper())
        or {}
    )


def _attach_owner(row: dict, idx: dict, owner_raw: str) -> dict:
    raw = (owner_raw or "").strip()
    rec = _lookup_owner(idx, raw)
    row["owner_raw"] = raw
    row["owner_id"] = rec.get("player_id") or raw
    row["owner_name"] = rec.get("name") or ""
    row["last_seen"] = rec.get("last_seen") or ""
    row["character_state"] = rec.get("character_state") or ""
    row["transferred"] = bool(rec.get("transferred"))
    state_l = (rec.get("character_state") or "").lower()
    if not raw:
        row["orphan"] = True
        row["orphan_reason"] = "unowned / world"
        row["owner_id"] = ""
    elif not rec:
        row["orphan"] = True
        row["orphan_reason"] = "no matching player_state"
    elif rec.get("transferred") and not rec.get("last_seen"):
        row["orphan"] = True
        row["orphan_reason"] = "transferred, never seen here"
    elif not rec.get("last_seen"):
        row["orphan"] = True
        row["orphan_reason"] = "never seen on this world"
    elif state_l in ("deleted",):
        row["orphan"] = True
        row["orphan_reason"] = rec.get("character_state") or state_l
    else:
        row["orphan"] = False
        row["orphan_reason"] = ""
    return row


def _list_table(table: str, kind: str, idx: dict, where: str = "") -> list[dict]:
    t = _ident(table)
    cols = table_cols(t)
    if not cols:
        return []
    idc = _first_col(cols, ("id", "guid", "uid"))
    mapc = _first_col(cols, ("map", "map_name", "building_blueprint_map", "partition", "world"))
    namec = _first_col(cols, ("name", "base_backup_name", "display_name", "class_name", "template_name", "vehicle_name"))
    ownerc = _first_col(
        cols,
        (
            "last_placed_by_player_id",
            "player_id",
            "owner_id",
            "last_edited_by_player_id",
            "character_id",
            "account_id",
            "player_controller_id",
            "controller_id",
            "owner_account_id",
        ),
    )
    itemc = _first_col(cols, ("item_id", "class_name", "vehicle_class", "template"))
    if not idc:
        return []
    sel = ["%s::text" % idc]
    sel.append("%s::text" % mapc if mapc else "''")
    sel.append("%s::text" % namec if namec else "''")
    sel.append("%s::text" % ownerc if ownerc else "''")
    sel.append("%s::text" % itemc if itemc else "''")
    sql = "SELECT %s FROM dune.%s" % (", ".join(sel), t)
    if where:
        sql += " WHERE " + where
    sql += " LIMIT 400"
    out = []
    for r in _psql_rows(sql):
        rec = {
            "kind": kind,
            "source": t,
            "id": r[0] if r else "",
            "map": r[1] if len(r) > 1 else "",
            "name": r[2] if len(r) > 2 else "",
            "class_name": r[4] if len(r) > 4 else "",
        }
        _attach_owner(rec, idx, r[3] if len(r) > 3 else "")
        out.append(rec)
    return out


def world_objects(kind: str = "all") -> dict:
    """Read-only listing. SELECT only; never UPDATE/DELETE.

    Funcom stores building.owner_id and actors.owner_account_id as null on this
    world. Owners come from building_instances.last_placed_by_player_id
    (controller id) and permission_actor_rank.player_id (rank 1).
    """
    idx = _owner_index()
    bases: list[dict] = []
    vehicles: list[dict] = []

    for r in _psql_rows(
        "SELECT b.id::text, COALESCE(a.map,''), COALESCE(a.class,''), "
        "COALESCE((SELECT bi.last_placed_by_player_id::text FROM dune.building_instances bi "
        " WHERE bi.building_id = b.id AND COALESCE(bi.last_placed_by_player_id,0) <> 0 "
        " GROUP BY bi.last_placed_by_player_id ORDER BY COUNT(*) DESC LIMIT 1), ''), "
        "COALESCE((SELECT COUNT(*)::text FROM dune.building_instances bi WHERE bi.building_id = b.id),'0') "
        "FROM dune.buildings b LEFT JOIN dune.actors a ON a.id = b.id LIMIT 400"
    ):
        rec = {
            "kind": "building",
            "source": "buildings",
            "id": r[0] if r else "",
            "map": r[1] if len(r) > 1 else "",
            "class_name": r[2] if len(r) > 2 else "",
            "pieces": r[4] if len(r) > 4 else "0",
        }
        rec["name"] = "%s (%s pieces)" % (_short_class(rec["class_name"]) or "building", rec["pieces"])
        _attach_owner(rec, idx, r[3] if len(r) > 3 else "")
        bases.append(rec)

    for r in _psql_rows(
        "SELECT pa.actor_id::text, COALESCE(a.map,''), COALESCE(pa.actor_name,''), "
        "COALESCE(a.class,''), r.player_id::text "
        "FROM dune.permission_actor pa "
        "JOIN dune.permission_actor_rank r ON r.permission_actor_id = pa.actor_id AND r.rank = 1 "
        "LEFT JOIN dune.actors a ON a.id = pa.actor_id "
        "WHERE pa.actor_type = 4 LIMIT 400"
    ):
        rec = {
            "kind": "claim",
            "source": "permission_actor",
            "id": r[0] if r else "",
            "map": r[1] if len(r) > 1 else "",
            "name": (r[2] if len(r) > 2 else "") or _short_class(r[3] if len(r) > 3 else ""),
            "class_name": r[3] if len(r) > 3 else "",
        }
        _attach_owner(rec, idx, r[4] if len(r) > 4 else "")
        bases.append(rec)

    bases.extend(_list_table("building_blueprints", "blueprint", idx))
    bases.extend(_list_table("base_backups", "backup", idx))

    for r in _psql_rows(
        "SELECT v.id::text, COALESCE(a.map,''), COALESCE(a.class,''), "
        "COALESCE((SELECT r.player_id::text FROM dune.permission_actor_rank r "
        " JOIN dune.permission_actor pa ON pa.actor_id = r.permission_actor_id "
        " WHERE pa.actor_id = v.id AND r.rank = 1 LIMIT 1), ''), "
        "COALESCE((SELECT rv.character_id::text FROM dune.recovered_vehicles rv "
        " WHERE rv.vehicle_id = v.id LIMIT 1), '') "
        "FROM dune.vehicles v LEFT JOIN dune.actors a ON a.id = v.id LIMIT 400"
    ):
        cls = r[2] if len(r) > 2 else ""
        if "Fabricator" in (cls or ""):
            continue
        rec = {
            "kind": "vehicle",
            "source": "vehicles",
            "id": r[0] if r else "",
            "map": r[1] if len(r) > 1 else "",
            "class_name": cls,
            "name": _short_class(cls) or ("vehicle " + (r[0] or "")),
        }
        owner = (r[3] if len(r) > 3 else "") or (r[4] if len(r) > 4 else "")
        _attach_owner(rec, idx, owner)
        if (r[4] if len(r) > 4 else "") and not (r[3] if len(r) > 3 else ""):
            rec["name"] = (rec.get("name") or "") + " (recovered)"
        vehicles.append(rec)

    seen_owners: dict[str, dict] = {}
    for item in bases + vehicles:
        if not item.get("orphan"):
            continue
        oid = item.get("owner_id") or item.get("owner_raw") or "(unowned)"
        rec = seen_owners.get(oid)
        if rec is None:
            rec = {
                "owner_id": oid if oid != "(unowned)" else "",
                "owner_name": item.get("owner_name") or ("unowned / world" if oid == "(unowned)" else ""),
                "last_seen": item.get("last_seen") or "",
                "reason": item.get("orphan_reason") or "",
                "bases": 0,
                "vehicles": 0,
            }
            seen_owners[oid] = rec
        if item.get("kind") == "vehicle":
            rec["vehicles"] += 1
        else:
            rec["bases"] += 1
    orphans = list(seen_owners.values())
    if kind == "vehicles":
        return {"ok": True, "items": vehicles, "count": len(vehicles)}
    if kind == "orphans":
        return {"ok": True, "items": orphans, "count": len(orphans)}
    if kind == "bases":
        return {"ok": True, "items": bases, "count": len(bases)}
    return {
        "ok": True,
        "bases": bases,
        "vehicles": vehicles,
        "orphans": orphans,
        "count": len(bases) + len(vehicles),
    }

def player_row(pid: str) -> dict:
    pid = M.normalize_player_id(pid).replace("'", "")
    rows = _psql_rows(
        "SELECT ps.character_name, ps.last_login_time::text, ps.online_status::text, "
        "ps.player_controller_id::text, ps.account_id::text, a.\"user\"::text, "
        "COALESCE(a.funcom_id,''), COALESCE(ps.player_pawn_id::text,''), "
        "COALESCE(f.faction_id::text,''), COALESCE(ps.id::text,''), "
        "COALESCE(ps.life_state::text,''), COALESCE(ps.character_state::text,''), "
        "COALESCE(a.platform_name,''), COALESCE(ps.last_avatar_activity::text,''), "
        "COALESCE(ps.transfer_count::text,'0'), "
        "COALESCE(ps.last_character_state_change::text,'') "
        "FROM dune.player_state ps "
        "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
        "LEFT JOIN dune.player_faction f ON f.actor_id = ps.player_pawn_id "
        "WHERE a.\"user\"::text ILIKE '%s' OR a.funcom_id::text ILIKE '%s' "
        "OR ps.account_id::text = '%s' LIMIT 1" % (pid, pid, pid)
    )
    if not rows:
        return {}
    r = rows[0]
    hid = (M.world_host_id() or "").upper()
    fls = r[5] if len(r) > 5 else pid
    fun = r[6] if len(r) > 6 else ""
    if hid and (fls or "").upper() == hid:
        fls = fun or pid
    return {
        "name": r[0] if len(r) > 0 else "",
        "last_login": r[1] if len(r) > 1 else "",
        "online_status": r[2] if len(r) > 2 else "",
        "controller_id": r[3] if len(r) > 3 else "",
        "account_id": r[4] if len(r) > 4 else "",
        "fls_id": fls,
        "funcom_id": fun,
        "pawn_id": r[7] if len(r) > 7 else "",
        "faction_id": r[8] if len(r) > 8 else "",
        "state_id": r[9] if len(r) > 9 else "",
        "life_state": r[10] if len(r) > 10 else "",
        "character_state": r[11] if len(r) > 11 else "",
        "platform": r[12] if len(r) > 12 else "",
        "last_seen": r[13] if len(r) > 13 else "",
        "transfer_count": r[14] if len(r) > 14 else "0",
        "transferred": (r[14].strip() not in ("", "0")) if len(r) > 14 else False,
        "last_state_change": r[15] if len(r) > 15 else "",
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
    bank_solari = "0"
    carried_solari = "0"
    for it in inventory:
        if str(it.get("template_id") or "") == "SolarisCoin":
            try:
                carried_solari = str(int(carried_solari) + int(it.get("qty") or 0))
            except (TypeError, ValueError):
                pass
    if ctrl:
        for r in _psql_rows(
            "SELECT currency_id::text, balance::text FROM dune.player_virtual_currency_balances "
            "WHERE player_controller_id::text = '%s'" % ctrl
        ):
            currency.append({"id": r[0], "balance": r[1] if len(r) > 1 else ""})
        ucols = table_cols("dune_exchange_users")
        ownc = _ident(_first_col(ucols, ("owner_id", "player_id", "user_id")))
        balc = _ident(_first_col(ucols, ("solari_balance", "solari", "balance", "currency_balance", "amount")))
        if ownc and balc and table_cols("dune_exchange_users"):
            for r in _psql_rows(
                "SELECT COALESCE(%s::text,'0') FROM dune.dune_exchange_users WHERE %s::text = '%s'"
                % (balc, ownc, ctrl)
            ):
                bank_solari = r[0] if r else "0"
                currency.append({"id": "solari_bank", "balance": bank_solari})
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
    firsts = load_presence_store().get("first_seen") or {}
    fs = firsts.get(pid) or firsts.get(base.get("fls_id") or "") or firsts.get((base.get("player_id") or "")) or {}
    first_seen = fs.get("ts") if isinstance(fs, dict) else ""
    return {
        "ok": True,
        "player": base,
        "inventory": inventory,
        "guilds": guilds,
        "currency": currency,
        "solari": {"carried": carried_solari, "bank": bank_solari},
        "first_seen": first_seen,
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
        "gates": c.get("gates") or {},
        "last_apply_ts": c.get("last_apply_ts"),
        "last_restart_ts": c.get("last_restart_ts"),
        "presence": c.get("presence") or {},
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
    pid = M.resolve_player_id(str(body.get("player_id") or ""))
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
        ok, msg = M.mq_publish(M.service_broadcast_fields(cancel=True, title="Restart", body="Cancelled"))
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
        if "gates" in body and isinstance(body.get("gates"), dict):
            g = dict(c.get("gates") or {})
            for k in ("grants", "wipe_inventory", "reset_progression", "teleport", "spawn_vehicle"):
                if k in body["gates"]:
                    g[k] = bool(body["gates"][k])
            c["gates"] = g
        if "presence" in body and isinstance(body.get("presence"), dict):
            p = dict(c.get("presence") or {})
            for k in ("discord_join", "discord_leave", "discord_maps", "restart_defer_if_online"):
                if k in body["presence"]:
                    p[k] = bool(body["presence"][k])
            c["presence"] = p
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
    global _LAST_ONLINE, _LAST_NAMES, _MAP_READY, _WAS_JOINABLE, _WAS_MODIFYING, _ONLINE_READY
    try:
        ip = M.lan_ip()
        st = M.world_status(ip)
    except Exception:
        return
    pres = presence_cfg()
    joinable = bool(st.get("joinable"))
    maps = st.get("maps") or []
    bg = st.get("battlegroup") or {}
    modifying = bool(bg.get("modifying"))
    if pres.get("discord_maps", True) and _ONLINE_READY:
        for m in maps:
            kind = str(m.get("kind") or "")
            ready = bool(m.get("ready"))
            prev = _MAP_READY.get(kind)
            if prev is True and not ready:
                webhook(
                    "map_down",
                    "%s not Ready (%s %s)" % (kind, m.get("phase") or "", m.get("ready_col") or ""),
                )
            if kind:
                _MAP_READY[kind] = ready
        if _WAS_MODIFYING is False and modifying:
            webhook("map_down", "Gateway / battlegroup Modifying")
        if _WAS_JOINABLE and not joinable:
            survival_ok = bool(st.get("survival_ok"))
            overmap_ok = bool(st.get("overmap_ok"))
            if survival_ok and overmap_ok:
                webhook("map_down", "World not joinable: " + ", ".join(st.get("join_notes") or []))
    _WAS_JOINABLE = joinable
    _WAS_MODIFYING = modifying
    players, _e = M.load_players()
    online = {p.get("player_id") for p in players if p.get("online") and p.get("player_id")}
    names = {p.get("player_id"): p.get("name") or "" for p in players if p.get("player_id")}
    store = load_presence_store()
    firsts = store.setdefault("first_seen", {})
    now = time.time()
    store_changed = False
    for p in players:
        pid = p.get("player_id")
        if not pid:
            continue
        if pid not in firsts:
            firsts[pid] = {"ts": now, "name": p.get("name") or ""}
            store_changed = True
    if store_changed:
        M.save_json_file(PRESENCE_FILE, store)
    if _ONLINE_READY:
        for pid in sorted(online - _LAST_ONLINE):
            name = names.get(pid) or _LAST_NAMES.get(pid) or ""
            if pres.get("discord_join", True):
                webhook("join", "%s %s" % (name or "player", pid[:12]))
            w = cfg().get("welcome") or {}
            if w.get("enabled") and w.get("items"):
                grant_welcome(pid)
        for pid in sorted(_LAST_ONLINE - online):
            name = _LAST_NAMES.get(pid) or ""
            if pres.get("discord_leave", True):
                webhook("leave", "%s %s" % (name or "player", pid[:12]))
    _LAST_ONLINE = online
    _LAST_NAMES = names
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
        remain = max(30, int(at - now))
        M.mq_publish(
            M.service_broadcast_fields(
                kind="ServerShutdown",
                title="Restart",
                body="World restart scheduled from admin panel",
                shutdown_type="Restart",
                shutdown_duration=remain,
                frequency=60,
                at=int(at),
            )
        )
        sch["announced"] = True
        c = cfg()
        c["schedule"] = sch
        save_cfg(c)
        webhook("restart", "Restart countdown started")
    if now >= at:
        deferred = restart_deferred_reason(len(online))
        if deferred:
            if not sch.get("deferred"):
                webhook("restart", deferred)
                sch["deferred"] = True
                c = cfg()
                c["schedule"] = sch
                save_cfg(c)
            return
        webhook("restart", "Restarting battlegroup now")
        M.battlegroup("restart")
        c = cfg()
        c["schedule"] = None
        c["last_restart_ts"] = time.time()
        save_cfg(c)
        _SETTINGS_META_CACHE["t"] = 0.0
