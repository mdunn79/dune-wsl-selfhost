#!/usr/bin/env python3
"""LAN web admin for a Funcom Dune: Awakening WSL battlegroup.

Binds the host LAN IP on TCP 18889 (never 0.0.0.0). Token in
/home/dune/.dune/admin.token. Does not print Funcom JWT, DB, or RMQ secrets.

Player tools use Funcom's in-cluster ServerCommand path (RabbitMQ heartbeats /
notifications), the same envelope community managers use for KickPlayer,
AddItemToInventory, ServiceBroadcast, etc. Publish-ok means the broker took
the message; some effects still need a live in-game check.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOME = Path(os.environ.get("HOME", "/home/dune"))
DUNE = HOME / ".dune"
TOKEN_FILE = DUNE / "admin.token"
BANS_FILE = DUNE / "admin-bans.json"
WHITELIST_FILE = DUNE / "admin-whitelist.json"
AUDIT_FILE = DUNE / "admin-audit.jsonl"
LAN_FILE = DUNE / "lan-ip.conf"
LISTEN_PORT = int(os.environ.get("DUNE_ADMIN_PORT", "18889"))
COOKIE = "dune_admin"
AUTH_TOKEN_MQ = "Nu6VmPWUMvdPMeB7qErr"  # Funcom ServerCommand envelope (not a user secret)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9._-]{20,}")
HEX_ID_RE = re.compile(r"^[A-Fa-f0-9]{8,64}$")
FUNCOM_TAG_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}#\d{2,8}$")
LOGIN_HITS: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()
_NS_CACHE = {"t": 0.0, "v": ""}
_PLAYER_SQL: str | None = None

COMMON_ITEMS = [
    "Water",
    "Solari",
    "DewReaper",
    "T2MachineComponent",
    "T3MachineComponent",
    "T4MachineComponent",
    "T5MachineComponent",
    "T6MachineComponent",
    "SpiceMelange",
    "FuelCell",
    "WeldingWire",
    "AdvancedServok",
    "T3MiningGalleryComponent1",
    "ParticleCapacitor",
    "CarbideScraps",
    "PlastaniumIngot",
]

VEHICLES = [
    ("Sandbike", "T6"),
    ("Sandbike", "T6_Combat"),
    ("Buggy", "T6"),
    ("Buggy", "T6_Combat"),
    ("Ornithopter", "T6"),
    ("Ornithopter", "T6_Scout"),
]


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def lan_ip() -> str:
    if LAN_FILE.is_file():
        ip = LAN_FILE.read_text(encoding="utf-8", errors="replace").strip()
        if ip and ip != "127.0.0.1":
            return ip
    env = os.environ.get("DUNE_LAN_IP", "").strip()
    if env and env != "127.0.0.1":
        return env
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "eth0"],
            text=True,
            timeout=5,
        )
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            return m.group(1)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    raise SystemExit("ERROR: no LAN IP; write /home/dune/.dune/lan-ip.conf")


def run(
    cmd: list[str],
    timeout: int = 40,
    inp: str | None = None,
    *,
    redact_out: bool = False,
) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            input=inp,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = p.stdout or ""
        stderr = p.stderr or ""
        if p.returncode == 0:
            text = stdout
        else:
            text = (stdout + ("\n" + stderr if stderr else "")).strip()
            redact_out = True
        if redact_out:
            text = redact(text)
        return p.returncode, text
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError as e:
        return 127, str(e)


def redact(text: str) -> str:
    text = JWT_RE.sub("[redacted-jwt]", text)
    text = re.sub(r"(?i)(password|passwd|secret|token)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    return text


def ns() -> str:
    now = time.time()
    if _NS_CACHE["v"] and now - _NS_CACHE["t"] < 20:
        return _NS_CACHE["v"]
    code, out = run(
        [
            "sudo",
            "kubectl",
            "get",
            "ns",
            "--no-headers",
            "-o",
            "custom-columns=NAME:.metadata.name",
        ],
        timeout=20,
    )
    found = ""
    if code == 0:
        for line in out.splitlines():
            name = line.strip()
            if name.startswith("funcom-seabass-"):
                found = name
                break
    _NS_CACHE["t"] = now
    _NS_CACHE["v"] = found
    return found


def bg() -> str:
    n = ns()
    return n[len("funcom-seabass-") :] if n.startswith("funcom-seabass-") else ""


def world_host_id() -> str:
    m = re.search(r"(?i)sh-([0-9a-f]{16})", bg() or ns() or "")
    return m.group(1).upper() if m else ""


def kubectl_json(args: list[str], timeout: int = 30) -> dict | list | None:
    # Do not redact: pod JSON includes service-account "token" fields and
    # redact() used to turn those into invalid JSON, so the UI saw zero pods.
    code, out = run(["sudo", "kubectl", *args, "-o", "json"], timeout=timeout)
    if code != 0:
        return None
    start = out.find("{")
    if start < 0:
        start = out.find("[")
    if start < 0:
        return None
    try:
        return json.loads(out[start:])
    except json.JSONDecodeError:
        return None


def load_json_file(path: Path, default):
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def save_json_file(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, 0o600)


def ensure_token() -> str:
    DUNE.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.is_file() and TOKEN_FILE.stat().st_size >= 16:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return tok


def token_ok(got: str) -> bool:
    want = ensure_token().strip()
    got = (got or "").strip()
    if not got or not want:
        return False
    if len(got) != len(want):
        return False
    return hmac.compare_digest(got.encode("utf-8"), want.encode("utf-8"))


def audit(action: str, detail: dict) -> None:
    row = {"ts": _now(), "action": action}
    row.update(detail)
    try:
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        os.chmod(AUDIT_FILE, 0o600)
    except OSError:
        pass


def pod_names() -> list[str]:
    n = ns()
    if not n:
        return []
    code, out = run(
        [
            "sudo",
            "kubectl",
            "get",
            "pods",
            "-n",
            n,
            "--no-headers",
            "-o",
            "custom-columns=NAME:.metadata.name",
        ],
        timeout=20,
    )
    if code != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def pod_name(substr: str) -> str:
    for name in pod_names():
        if substr in name:
            return name
    return ""


def psql(sql: str) -> tuple[int, str]:
    n = ns()
    pod = pod_name("db-dbdepl-sts")
    if not n or not pod:
        return 1, "no database pod"
    last = (1, "psql failed")
    for user in ("dune", "postgres"):
        code, out = run(
            [
                "sudo",
                "kubectl",
                "exec",
                "-n",
                n,
                pod,
                "-c",
                "database",
                "--",
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "15432",
                "-U",
                user,
                "-d",
                "dune",
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-F",
                "\t",
                "-c",
                sql,
            ],
            timeout=40,
        )
        last = (code, out)
        if code == 0:
            return last
    return last


def qrel(schema_table: str) -> str:
    return ".".join('"%s"' % p.replace('"', "") for p in schema_table.split(".") if p)


def qcol(name: str) -> str:
    return '"%s"' % name.replace('"', "")


def load_table_map() -> tuple[dict[str, set[str]], str]:
    code, out = psql(
        "SELECT table_schema||'.'||table_name||'|'||string_agg(column_name, ',' ORDER BY ordinal_position) "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
        "GROUP BY table_schema, table_name"
    )
    if code != 0:
        return {}, (out or "schema probe failed")[:400]
    tables: dict[str, set[str]] = {}
    for line in out.splitlines():
        if "|" not in line:
            continue
        tname, cols = line.split("|", 1)
        tables[tname] = {c.strip().lower() for c in cols.split(",") if c.strip()}
    return tables, ""


def _pick_col(cols: set[str], names: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in cols}
    for n in names:
        if n in lower:
            return lower[n]
    return None


def _roster_player_id_sql() -> str:
    """Prefer FLS hex in accounts.user, but never the world HostId."""
    hid = (world_host_id() or "").replace("'", "")
    if hid:
        return (
            "COALESCE("
            "NULLIF(CASE WHEN upper(a.\"user\"::text) = '%s' THEN NULL "
            "ELSE NULLIF(a.\"user\"::text, '') END, ''), "
            "NULLIF(a.funcom_id::text, ''), "
            "ps.account_id::text)" % hid
        )
    return 'COALESCE(NULLIF(a."user"::text, \'\'), NULLIF(a.funcom_id::text, \'\'), ps.account_id::text)'


def discover_player_sql() -> tuple[str | None, str]:
    global _PLAYER_SQL
    if _PLAYER_SQL:
        return _PLAYER_SQL, ""
    known = [
        (
            "SELECT %s AS player_id, "
            "COALESCE(ps.character_name::text, '') AS name, "
            "COALESCE(ps.last_avatar_activity::text, '') AS last_seen, "
            "CASE WHEN lower(COALESCE(ps.online_status::text,'')) "
            "IN ('1','t','true','online') THEN '1' ELSE '0' END AS is_online, "
            "CASE WHEN COALESCE(ps.transfer_count, 0) > 0 THEN '1' ELSE '0' END AS transferred "
            "FROM dune.player_state ps "
            "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
            "ORDER BY 2, 1 LIMIT 2000" % _roster_player_id_sql()
        ),
        (
            "SELECT COALESCE(account_id::text, player_controller_id::text) AS player_id, "
            "COALESCE(character_name::text, '') AS name, "
            "COALESCE(last_avatar_activity::text, '') AS last_seen, "
            "CASE WHEN lower(COALESCE(online_status::text,'')) "
            "IN ('1','t','true','online') THEN '1' ELSE '0' END AS is_online, "
            "CASE WHEN COALESCE(transfer_count, 0) > 0 THEN '1' ELSE '0' END AS transferred "
            "FROM dune.player_state "
            "ORDER BY 2, 1 LIMIT 2000"
        ),
    ]
    last_err = ""
    for sql in known:
        code, out = psql(sql)
        if code == 0:
            _PLAYER_SQL = sql
            return sql, ""
        last_err = (out or "query failed")[:300]

    tables, err = load_table_map()
    if err:
        return None, err or last_err
    if not tables:
        return None, "no tables in game database"
    skip = ("patch", "schema", "migration", "rabbit", "applied", "import", "encrypted", "broken", "demo", "lore", "_log")
    name_prefs = ("character_name", "displayname", "display_name", "name", "username", "gamertag")
    id_prefs = ("fls_id", "flsid", "playerid", "player_id", "playfabid", "playfab_id", "funcom_id", "id")
    seen_prefs = (
        "last_avatar_activity",
        "last_seen",
        "lastseen",
        "last_played",
        "last_login_time",
        "last_login",
        "lastlogin",
        "updated_at",
        "updatedat",
        "login_time",
    )
    online_prefs = ("online_status", "is_online", "isonline", "online", "connected")

    def score(t: str, cols: set[str]) -> int:
        low = t.lower()
        if any(s in low for s in skip):
            return -1
        s = 0
        if low.endswith(".player_state"):
            s += 25
        if "character" in low and _pick_col(cols, name_prefs):
            s += 10
        if low.endswith(".accounts") or low.endswith(".user"):
            s += 6
        if _pick_col(cols, name_prefs):
            s += 5
        if _pick_col(cols, ("fls_id", "flsid", "playerid", "player_id")):
            s += 5
        elif _pick_col(cols, id_prefs):
            s += 2
        return s

    ranked = sorted(tables.items(), key=lambda kv: score(kv[0], kv[1]), reverse=True)
    if not ranked or score(ranked[0][0], ranked[0][1]) <= 0:
        return None, last_err or "no character/user table found"
    t, cols = ranked[0]
    idcol = _pick_col(cols, id_prefs)
    if not idcol:
        return None, "no player id column on %s" % t
    namecol = _pick_col(cols, name_prefs)
    seencol = _pick_col(cols, seen_prefs)
    oncol = _pick_col(cols, online_prefs)
    parts = ["%s::text AS player_id" % qcol(idcol)]
    parts.append("%s::text AS name" % qcol(namecol) if namecol else "'' AS name")
    parts.append("%s::text AS last_seen" % qcol(seencol) if seencol else "'' AS last_seen")
    if oncol:
        parts.append(
            "CASE WHEN lower(COALESCE(%s::text,'')) IN ('1','t','true','online') THEN '1' ELSE '0' END AS is_online"
            % qcol(oncol)
        )
    else:
        parts.append("'0' AS is_online")
    sql = (
        "SELECT %s FROM %s WHERE COALESCE(%s::text,'') <> '' "
        "ORDER BY 2, 1 LIMIT 2000"
        % (", ".join(parts), qrel(t), qcol(idcol))
    )
    _PLAYER_SQL = sql
    return sql, ""


def normalize_player_id(pid: str) -> str:
    s = (pid or "").strip()
    if s.lower().startswith("\\x"):
        s = s[2:]
    compact = s.replace("-", "")
    if HEX_ID_RE.match(compact):
        return compact
    return s


def _parse_xyz(text: str) -> dict | None:
    nums = re.findall(r"-?\d+(?:\.\d+)?", text or "")
    if len(nums) >= 3:
        try:
            return {"x": float(nums[0]), "y": float(nums[1]), "z": float(nums[2])}
        except ValueError:
            return None
    return None


def player_location(player_id: str) -> dict | None:
    pid = normalize_player_id(player_id).replace("'", "")
    if not pid:
        return None
    queries = [
        (
            "SELECT a.transform::text FROM dune.actors a "
            "JOIN dune.player_state ps ON ps.player_pawn_id = a.id "
            "LEFT JOIN dune.accounts acc ON acc.id = ps.account_id "
            "WHERE acc.\"user\"::text ILIKE '%s' OR acc.funcom_id::text ILIKE '%s' "
            "OR ps.account_id::text = '%s' LIMIT 1" % (pid, pid, pid)
        ),
        (
            "SELECT op.overmap_location::text FROM dune.overmap_players op "
            "JOIN dune.player_state ps ON ps.player_controller_id::text = op.player_id::text "
            "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
            "WHERE a.\"user\"::text ILIKE '%s' OR a.funcom_id::text ILIKE '%s' "
            "OR ps.account_id::text = '%s' LIMIT 1" % (pid, pid, pid)
        ),
        (
            "SELECT death_location::text FROM dune.player_state ps "
            "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
            "WHERE a.\"user\"::text ILIKE '%s' OR a.funcom_id::text ILIKE '%s' "
            "OR ps.account_id::text = '%s' LIMIT 1" % (pid, pid, pid)
        ),
    ]
    for q in queries:
        code, out = psql(q)
        if code == 0 and out.strip():
            loc = _parse_xyz(out.splitlines()[0])
            if loc:
                return loc
    code, out = psql(
        "SELECT table_schema||'.'||table_name||'|'||string_agg(column_name, ',') "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
        "AND (column_name ILIKE '%pos%x%' OR lower(column_name) IN ('x','locx')) "
        "GROUP BY table_schema, table_name"
    )
    if code != 0:
        return None
    for line in out.splitlines():
        if "pawn" not in line.lower() and "location" not in line.lower() and "transform" not in line.lower():
            continue
        tname = line.split("|")[0]
        cols = {c.strip().lower() for c in line.split("|", 1)[-1].split(",")}
        idcol = next((c for c in ("playerid", "player_id", "userid", "id") if c in cols), None)
        x = next((c for c in ("x", "locx", "posx", "positionx") if c in cols), None)
        y = next((c for c in ("y", "locy", "posy", "positiony") if c in cols), None)
        z = next((c for c in ("z", "locz", "posz", "positionz") if c in cols), None)
        if not (idcol and x and y and z):
            continue
        q = (
            "SELECT %s::float8, %s::float8, %s::float8 FROM %s "
            "WHERE %s::text ILIKE '%s' LIMIT 1" % (x, y, z, tname, idcol, pid)
        )
        c2, o2 = psql(q)
        if c2 == 0 and o2.strip():
            parts = o2.strip().split("\t")
            if len(parts) >= 3:
                try:
                    return {"x": float(parts[0]), "y": float(parts[1]), "z": float(parts[2])}
                except ValueError:
                    pass
    return None


def service_broadcast_fields(
    *,
    kind: str = "Generic",
    title: str = "Server",
    body: str = "",
    duration: int = 30,
    shutdown_type: str = "Restart",
    shutdown_duration: int = 600,
    frequency: int = 60,
    cancel: bool = False,
    at: int = 0,
) -> dict:
    """Inner ServerCommand for Funcom ServiceBroadcast. Title/Body live under BroadcastPayload."""
    title = str(title or "Server")
    body = str(body or "")
    loc = [
        {"Key": "en", "Title": title, "Body": body},
        {"Key": "en-US", "Title": title, "Body": body},
    ]
    if cancel or str(kind) == "ServerShutdown":
        now = int(time.time())
        ts = int(at) if at else now + int(shutdown_duration or 0)
        payload = {
            "ShutdownType": "Cancel" if cancel else str(shutdown_type or "Restart"),
            "DateTimestamp": now,
            "ShutdownDuration": 0 if cancel else int(shutdown_duration or 0),
            "ShutdownTimestamp": now if cancel else ts,
            "BroadcastFrequency": int(frequency or 60),
            "LocalizedText": loc,
        }
        if cancel:
            payload["ShouldCancel"] = True
        return {
            "ServerCommand": "ServiceBroadcast",
            "BroadcastType": "ServerShutdown",
            "BroadcastPayload": payload,
        }
    return {
        "ServerCommand": "ServiceBroadcast",
        "BroadcastType": "Generic",
        "BroadcastPayload": {
            "BroadcastDuration": int(duration or 30),
            "LocalizedText": loc,
        },
    }


def mq_publish(fields: dict) -> tuple[bool, str]:
    n = ns()
    pod = pod_name("mq-game-sts")
    if not n or not pod:
        return False, "no mq-game pod"
    inner = json.dumps(fields, separators=(",", ":"))
    outer = json.dumps(
        {"Version": 2, "AuthToken": AUTH_TOKEN_MQ, "MessageContent": inner},
        separators=(",", ":"),
    )
    env_b64 = base64.b64encode(outer.encode("utf-8")).decode("ascii")
    msg_id = "dune-admin-%d" % int(time.time() * 1000)
    erlang = (
        'Outer = base64:decode(<<"%s">>),'
        'XName = rabbit_misc:r(<<"/">>, exchange, <<"heartbeats">>),'
        "X = rabbit_exchange:lookup_or_die(XName),"
        'MsgId = <<"%s">>,'
        'P = {list_to_atom("P_basic"), <<"Content">>, undefined, [], undefined,'
        " undefined, undefined, undefined, undefined, MsgId, undefined,"
        ' undefined, <<"fls">>, <<"fls_backend">>, undefined},'
        "Content = rabbit_basic:build_content(P, Outer),"
        '{ok, Msg} = rabbit_basic:message(XName, <<"notifications">>, Content),'
        "rabbit_queue_type:publish_at_most_once(X, Msg)."
    ) % (env_b64, msg_id)
    last = "rabbitmqctl eval failed"
    for ctl in ("/opt/rabbitmq/sbin/rabbitmqctl", "rabbitmqctl", "/opt/rabbitmq/escript/rabbitmqctl"):
        code, out = run(
            ["sudo", "kubectl", "exec", "-n", n, pod, "--", ctl, "eval", erlang],
            timeout=30,
        )
        if code == 0:
            return True, "published %s" % fields.get("ServerCommand", "command")
        last = out or last
    return False, last[:800]


def maps_from_pods() -> list[dict]:
    n = ns()
    rows: list[dict] = []
    if not n:
        return rows
    code, out = run(["sudo", "kubectl", "get", "pods", "-n", n, "--no-headers"], timeout=20)
    if code != 0:
        return rows
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, ready, phase = parts[0], parts[1], parts[2]
        if "sg-survival" not in name and "sg-overmap" not in name and "sgw-deploy" not in name:
            continue
        if "sgw-deploy" in name:
            kind = "Gateway"
        else:
            kind = "Survival" if "survival" in name else "Overmap"
        rows.append(
            {
                "name": name,
                "kind": kind,
                "phase": phase,
                "ready": ready == "1/1" and phase == "Running",
                "ready_col": ready,
            }
        )
    return rows


def is_updating() -> bool:
    code, out = run(["ps", "-eo", "args="], timeout=8)
    if code != 0:
        return False
    for line in out.splitlines():
        if re.search(r"steamcmd|app_update\s+4754530|dune-maintain\.sh", line):
            if "dune-admin" in line:
                continue
            return True
    return False


def join_ports(ip: str) -> dict:
    code, out = run(["sudo", "ss", "-ltn"], timeout=8)
    listening = out if code == 0 else ""
    return {
        "rmq_31982": (":31982" in listening),
        "director_31519": (":31519" in listening),
        "filebrowser_18888": (":18888" in listening),
        "admin_18889": (":18889" in listening),
        "lan_ip": ip,
    }


def advertise_status() -> str:
    script = HOME / ".dune/bin/dune-set-advertise-ip.sh"
    if not script.is_file():
        return ""
    _code, out = run([str(script), "--status"], timeout=20)
    return out.strip()


def serverstats_players() -> list[dict]:
    n = ns()
    if not n:
        return []
    data = kubectl_json(["get", "serverstats", "-n", n])
    found = []
    if not isinstance(data, dict):
        return found
    items = data.get("items")
    if items is None and data.get("kind"):
        items = [data]
    hid = world_host_id()
    for item in items or []:
        st = item.get("status") or {}
        blob = json.dumps(st)
        for m in re.finditer(r'"([A-Fa-f0-9]{16,})"', blob):
            hx = m.group(1)
            if hid and hx.upper() == hid:
                continue
            found.append({"player_id": hx, "source": "serverstats"})
        count = st.get("playerCount") or st.get("players") or st.get("numPlayers")
        if isinstance(count, int):
            found.append({"player_count": count, "source": "serverstats"})
    return found


def load_players() -> tuple[list[dict], str]:
    sql, err = discover_player_sql()
    players: list[dict] = []
    if sql:
        code, out = psql(sql)
        if code != 0:
            err = (out or "player query failed")[:400]
        else:
            err = ""
            for line in out.splitlines():
                parts = line.split("\t")
                if not parts or not parts[0]:
                    continue
                pid = normalize_player_id(parts[0].strip())
                if pid.lower() in ("player_id", "id"):
                    continue
                xfer = False
                if len(parts) > 4:
                    xfer = parts[4].strip().lower() in ("1", "t", "true")
                players.append(
                    {
                        "player_id": pid,
                        "name": parts[1] if len(parts) > 1 else "",
                        "last_seen": parts[2] if len(parts) > 2 else "",
                        "online": (parts[3].strip() == "1") if len(parts) > 3 else False,
                        "transferred": xfer,
                    }
                )
    hid = world_host_id()
    for p in players:
        pid = (p.get("player_id") or "").upper()
        if hid and pid == hid:
            p["player_id"] = ""
            extra = "Funcom stored the world HostId as this account's user field"
            p["note"] = ((p.get("note") or "").strip() + " " + extra).strip()
        elif "#" in (p.get("player_id") or ""):
            extra = "Funcom id (this world's accounts.user is the HostId, not an FLS hex)"
            p["note"] = ((p.get("note") or "").strip() + " " + extra).strip()
    players = [p for p in players if p.get("player_id") or p.get("name")]
    online_ids = set()
    roster = {(p.get("player_id") or "").upper() for p in players if p.get("player_id")}
    for row in serverstats_players():
        if row.get("player_id"):
            pid = normalize_player_id(row["player_id"]).upper()
            if hid and pid == hid:
                continue
            if pid in roster:
                online_ids.add(pid)
    bans = {b.get("player_id", "").upper() for b in load_json_file(BANS_FILE, []) if isinstance(b, dict)}
    wl = load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []})
    wl_ids = {str(x).upper() for x in (wl.get("ids") or [])}
    for p in players:
        pid = (p.get("player_id") or "").upper()
        if pid in online_ids:
            p["online"] = True
        p["banned"] = pid in bans
        p["whitelisted"] = pid in wl_ids
    players.sort(key=lambda p: (not p.get("online"), (p.get("name") or "").lower(), p.get("player_id") or ""))
    enrich = globals().get("enrich_players")
    if callable(enrich):
        players = enrich(players)
    return players, err


def enforce_bans_and_whitelist() -> None:
    bans = load_json_file(BANS_FILE, [])
    now = time.time()
    live = []
    expired = False
    for b in bans if isinstance(bans, list) else []:
        if not isinstance(b, dict):
            continue
        exp = b.get("expires")
        if exp:
            try:
                if float(exp) < now:
                    expired = True
                    continue
            except (TypeError, ValueError):
                pass
        live.append(b)
    if expired:
        save_json_file(BANS_FILE, live)
    bans = live
    wl = load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []})
    players, _err = load_players()
    ban_ids = {str(b.get("player_id", "")).upper() for b in bans if isinstance(b, dict)}
    allow = {str(x).upper() for x in (wl.get("ids") or [])}
    for p in players:
        pid = (p.get("player_id") or "")
        if not pid:
            continue
        up = pid.upper()
        if up in ban_ids and p.get("online") and HEX_ID_RE.match(normalize_player_id(pid)):
            ok, msg = mq_publish({"ServerCommand": "KickPlayer", "PlayerId": normalize_player_id(pid)})
            audit("auto-kick-ban", {"player_id": pid, "ok": ok, "msg": msg[:200]})
        elif wl.get("enabled") and allow and up not in allow and p.get("online") and HEX_ID_RE.match(normalize_player_id(pid)):
            ok, msg = mq_publish({"ServerCommand": "KickPlayer", "PlayerId": pid})
            audit("auto-kick-whitelist", {"player_id": pid, "ok": ok, "msg": msg[:200]})


def pod_logs(kind: str, since: str = "15m") -> str:
    n = ns()
    key = {
        "survival": "sg-survival",
        "overmap": "sg-overmap",
        "director": "bgd-deploy",
        "gateway": "sgw-deploy",
        "textrouter": "tr-deploy",
    }.get(kind, "sg-survival")
    pod = pod_name(key)
    if not n or not pod:
        return "no pod"
    _code, out = run(
        ["sudo", "kubectl", "logs", "-n", n, pod, "--since=" + since, "--tail=200"],
        timeout=25,
        redact_out=True,
    )
    return out[-24000:]


def world_status(ip: str) -> dict:
    maps = maps_from_pods()
    survival_ok = any(m["kind"] == "Survival" and m["phase"] == "Running" and m["ready"] for m in maps)
    overmap_ok = any(m["kind"] == "Overmap" and m["phase"] == "Running" and m["ready"] for m in maps)
    ports = join_ports(ip)
    st = advertise_status()
    updating = is_updating()
    players, _perr = load_players()
    online_n = sum(1 for p in players if p.get("online"))
    notes = []
    if updating:
        notes.append("Steam/maintain is running (depot update)")
    if not maps:
        notes.append("map pods not listed")
    if not survival_ok:
        notes.append("Survival is not 1/1 Running")
    if not overmap_ok:
        notes.append("Overmap is not 1/1 Running")
    if any(m["kind"] == "Gateway" and not m["ready"] for m in maps):
        notes.append("Gateway is not 1/1 Running")
    if not ports.get("rmq_31982"):
        notes.append("join TCP 31982 is down")
    if not ports.get("director_31519"):
        notes.append("director TCP 31519 is down")
    joinable = survival_ok and overmap_ok and bool(ports.get("rmq_31982")) and bool(ports.get("director_31519"))
    payload = {
        "ns": ns(),
        "bg": bg(),
        "maps": maps,
        "joinable": joinable,
        "updating": updating,
        "join_notes": notes,
        "survival_ok": survival_ok,
        "overmap_ok": overmap_ok,
        "ports": ports,
        "advertise": st,
        "player_count_known": online_n,
        "player_count_roster": len(players),
        "filebrowser": "http://%s:18888" % ip,
        "director": "http://%s:31519" % ip,
        "admin": "http://%s:%d" % (ip, LISTEN_PORT),
    }
    enrich = globals().get("enrich_status")
    return enrich(payload) if callable(enrich) else payload


def battlegroup(action: str, extra: list[str] | None = None) -> tuple[int, str]:
    cmd = [str(HOME / ".dune/bin/battlegroup"), action]
    if extra:
        cmd.extend(extra)
    return run(cmd, timeout=180)


def resolve_player_id(pid: str) -> str:
    """GM commands need accounts.user hex, even when that hex is the world HostId."""
    raw = (pid or "").strip()
    n = normalize_player_id(raw)
    hid = world_host_id()
    q = raw.replace("'", "").replace("%", "").replace("\\", "")
    if q:
        sql = (
            "SELECT a.\"user\"::text, a.funcom_id::text FROM dune.player_state ps "
            "LEFT JOIN dune.accounts a ON a.id = ps.account_id "
            "WHERE a.funcom_id::text ILIKE '%s' OR ps.character_name::text ILIKE '%s' "
            "OR a.\"user\"::text ILIKE '%s' OR ps.account_id::text = '%s' "
            "LIMIT 1" % (q, q, q, q)
        )
        code, out = psql(sql)
        if code == 0 and out.strip():
            parts = out.splitlines()[0].split("\t")
            user = normalize_player_id((parts[0] if parts else "") or "")
            fun = (parts[1] if len(parts) > 1 else "").strip()
            if user and HEX_ID_RE.match(user):
                return user
            if fun:
                return fun
    if n and HEX_ID_RE.match(n) and (not hid or n.upper() != hid):
        return n
    return n or raw


def resolve_item_name(name: str) -> str:
    raw = (name or "").strip()
    if " — " in raw:
        raw = raw.rsplit(" — ", 1)[-1].strip()
    key = re.sub(r"[^a-z0-9]+", "", raw.lower())
    aliases = {
        "calibratedservok": "T3MiningGalleryComponent1",
        "calibratedservoks": "T3MiningGalleryComponent1",
        "t3mininggallerycomponent1": "T3MiningGalleryComponent1",
    }
    if key in aliases:
        return aliases[key]
    fn = globals().get("catalog")
    items = fn().get("items", []) if callable(fn) else []
    low = raw.lower()
    for row in items:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        if str(row[1]).lower() == low or str(row[0]).lower() == low:
            return str(row[1])
    return raw


def do_action(body: dict) -> dict:
    op = str(body.get("op") or "")
    raw_pid = str(body.get("player_id") or "").strip()
    hid = world_host_id()
    if raw_pid and hid and normalize_player_id(raw_pid).upper() == hid:
        return {
            "ok": False,
            "error": "that is the world HostId, not a player id. Players → your character → Use",
        }
    pid = resolve_player_id(raw_pid)
    confirm = bool(body.get("confirm"))
    if pid and pid != "*" and not HEX_ID_RE.match(pid) and not FUNCOM_TAG_RE.match(pid) and op not in ("locate", "save-note"):
        return {"ok": False, "error": "player_id must be an FLS hex or Funcom id (name#digits) from Players → Use"}
    body["player_id"] = pid

    prep = globals().get("prepare_gm")
    if callable(prep):
        blocked = prep(body)
        if blocked is not None:
            return blocked

    destructive = {
        "stop",
        "restart",
        "clean-inventory",
        "reset-progression",
        "import-backup",
    }
    if op in destructive and not confirm:
        return {"ok": False, "error": "confirm required"}

    if op == "start":
        code, out = battlegroup("start")
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "stop":
        code, out = battlegroup("stop")
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "restart":
        code, out = battlegroup("restart")
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "repair":
        code, out = run([str(HOME / ".dune/bin/dune-ensure-runtime.sh")], timeout=180)
        code2, out2 = run(
            ["env", "SKIP_FLS_DNS=1", str(HOME / ".dune/bin/dune-ensure-join.sh")],
            timeout=60,
        )
        return {"ok": code == 0 and code2 == 0, "out": (out + "\n" + out2)[-4000:]}
    if op == "backup":
        name = "web-%s" % time.strftime("%Y%m%d-%H%M%S")
        code, out = battlegroup("backup", [name])
        return {"ok": code == 0, "out": out[-4000:], "name": name}
    if op == "advertise-auto":
        code, out = run([str(HOME / ".dune/bin/dune-set-advertise-ip.sh"), "auto"], timeout=90)
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "advertise-lan":
        ip = lan_ip()
        code, out = run([str(HOME / ".dune/bin/dune-set-advertise-ip.sh"), ip], timeout=90)
        return {"ok": code == 0, "out": out[-4000:]}
    if op == "kick":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish({"ServerCommand": "KickPlayer", "PlayerId": pid})
        return {"ok": ok, "out": msg}
    if op == "ban":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        bans = load_json_file(BANS_FILE, [])
        rec = None
        for b in bans:
            if isinstance(b, dict) and str(b.get("player_id", "")).upper() == pid.upper():
                rec = b
                break
        if rec is None:
            rec = {"player_id": pid, "name": str(body.get("name") or ""), "ts": _now()}
            bans.append(rec)
        rec["reason"] = str(body.get("reason") or rec.get("reason") or "banned from admin panel")
        rec["name"] = str(body.get("name") or rec.get("name") or "")
        if body.get("expires"):
            try:
                rec["expires"] = float(body.get("expires"))
            except (TypeError, ValueError):
                rec.pop("expires", None)
        else:
            rec.pop("expires", None)
        save_json_file(BANS_FILE, bans)
        ok, msg = mq_publish({"ServerCommand": "KickPlayer", "PlayerId": pid})
        return {"ok": True, "out": "listed; kick: " + msg, "kicked": ok}
    if op == "unban":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        bans = [
            b
            for b in load_json_file(BANS_FILE, [])
            if not (isinstance(b, dict) and str(b.get("player_id", "")).upper() == pid.upper())
        ]
        save_json_file(BANS_FILE, bans)
        return {"ok": True, "out": "unbanned"}
    if op == "whitelist-add":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        wl = load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []})
        ids = [str(x) for x in (wl.get("ids") or [])]
        if pid not in ids:
            ids.append(pid)
        wl["ids"] = ids
        save_json_file(WHITELIST_FILE, wl)
        return {"ok": True, "out": "whitelisted"}
    if op == "whitelist-remove":
        wl = load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []})
        wl["ids"] = [str(x) for x in (wl.get("ids") or []) if str(x).upper() != pid.upper()]
        save_json_file(WHITELIST_FILE, wl)
        return {"ok": True, "out": "removed"}
    if op == "whitelist-enable":
        wl = load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []})
        enabled = bool(body.get("enabled"))
        ids = [str(x) for x in (wl.get("ids") or [])]
        if enabled and not ids:
            return {"ok": False, "error": "whitelist is empty; add people first or everyone online would be kicked"}
        wl["enabled"] = enabled
        save_json_file(WHITELIST_FILE, wl)
        return {"ok": True, "out": "whitelist enabled=%s" % wl["enabled"]}
    if op == "broadcast":
        title = str(body.get("title") or "Server")
        text = str(body.get("body") or "").strip()
        kind = str(body.get("broadcast_type") or "Generic")
        cancel = bool(body.get("cancel"))
        if kind != "ServerShutdown" and not cancel and not text:
            return {"ok": False, "error": "type a message in the Broadcast box"}
        fields = service_broadcast_fields(
            kind=kind,
            title=title,
            body=text,
            duration=int(body.get("duration") or 30),
            shutdown_type=str(body.get("shutdown_type") or "Restart"),
            shutdown_duration=int(body.get("shutdown_duration") or 600),
            frequency=int(body.get("frequency") or 60),
            cancel=cancel,
        )
        ok, msg = mq_publish(fields)
        return {"ok": ok, "out": msg}
    if op == "grant-item":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        item = resolve_item_name(str(body.get("item") or ""))
        if not item:
            return {"ok": False, "error": "item required (Funcom FName, e.g. T2MachineComponent)"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "AddItemToInventory",
                "PlayerId": pid,
                "ItemName": item,
                "Quantity": int(body.get("qty") or 1),
                "Durability": float(body.get("durability") or 1.0),
            }
        )
        return {"ok": ok, "out": msg, "item": item}
    if op == "award-xp":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "AwardXP",
                "PlayerId": pid,
                "Experience": int(body.get("xp") or 1000),
            }
        )
        return {"ok": ok, "out": msg}
    if op == "skill-points":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "SkillsSetUnspentSkillPoints",
                "PlayerId": pid,
                "SkillPoints": int(body.get("points") or 0),
            }
        )
        return {"ok": ok, "out": msg}
    if op == "refill-water":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "UpdateAllWaterFillables",
                "PlayerId": pid,
                "WaterAmount": int(body.get("water") or 1000000),
            }
        )
        return {"ok": ok, "out": msg}
    if op == "teleport":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "TeleportTo",
                "PlayerId": pid,
                "X": float(body.get("x")),
                "Y": float(body.get("y")),
                "Z": float(body.get("z")),
            }
        )
        return {"ok": ok, "out": msg}
    if op == "locate":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        loc = player_location(pid)
        return {"ok": loc is not None, "location": loc, "out": "ok" if loc else "no pawn coords in DB"}
    if op == "spawn-vehicle":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        loc = player_location(pid) or {}
        typed = body.get("x") not in (None, "")
        try:
            x = float(body.get("x") if typed else loc.get("x"))
            y = float(body.get("y") if typed else loc.get("y"))
            z = float(body.get("z") if typed else loc.get("z"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "no coordinates; Locate the player or type X/Y/Z (will not spawn at 0,0,0)"}
        if not typed and x == 0 and y == 0 and z == 0:
            return {"ok": False, "error": "no coordinates; Locate the player or type X/Y/Z"}
        ok, msg = mq_publish(
            {
                "ServerCommand": "SpawnVehicleAt",
                "PlayerId": pid,
                "ClassName": str(body.get("vehicle") or "Sandbike"),
                "TemplateName": str(body.get("template") or "T6"),
                "X": x,
                "Y": y,
                "Z": z,
                "Persistent": 1.0,
            }
        )
        return {"ok": ok, "out": msg, "at": {"x": x, "y": y, "z": z}}
    if op == "clean-inventory":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish({"ServerCommand": "CleanPlayerInventory", "PlayerId": pid})
        return {"ok": ok, "out": msg}
    if op == "reset-progression":
        if not pid:
            return {"ok": False, "error": "player_id required"}
        ok, msg = mq_publish({"ServerCommand": "ResetProgression", "PlayerId": pid})
        return {"ok": ok, "out": msg}
    extra = globals().get("extra_action")
    if callable(extra):
        got = extra(body)
        if got is not None:
            return got
    return {"ok": False, "error": "unknown op"}



HTML = ""  # UI is dune-admin.html


class Handler(BaseHTTPRequestHandler):
    server_version = "DuneAdmin/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys_stderr = __import__("sys").stderr
        line = "[%s] %s" % (_now(), fmt % args)
        if "admin.token" in line or "password" in line.lower():
            return
        print(line, file=sys_stderr)

    def _ip(self) -> str:
        return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

    def _got_token(self) -> str:
        h = (self.headers.get("X-Admin-Token") or "").strip()
        if h:
            return h
        ck = SimpleCookie()
        if "Cookie" in self.headers:
            ck.load(self.headers["Cookie"])
        if COOKIE in ck:
            return ck[COOKIE].value
        q = parse_qs(urlparse(self.path).query)
        return (q.get("token") or [""])[0]

    def _auth(self) -> bool:
        return token_ok(self._got_token())

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8", extra: list | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict, extra: list | None = None) -> None:
        raw = json.dumps(obj, default=str).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8", extra)

    def _login_ok(self) -> bool:
        ip = self._ip()
        now = time.time()
        with LOGIN_LOCK:
            hits = [t for t in LOGIN_HITS.get(ip, []) if now - t < 60]
            if len(hits) >= 8:
                LOGIN_HITS[ip] = hits
                return False
            hits.append(now)
            LOGIN_HITS[ip] = hits
        return True

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        path = u.path
        if path == "/healthz":
            self._json(200, {"ok": True})
            return
        authed = self._auth()
        if path in ("/", "/index.html"):
            extra = None
            if authed:
                extra = [("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=/" % (COOKIE, ensure_token()))]
            self._send(200, page_html().encode("utf-8"), extra=extra)
            return
        if not authed:
            self._json(401, {"ok": False, "error": "auth"})
            return
        ip = lan_ip()
        if path == "/api/status":
            self._json(200, world_status(ip))
            return
        if path == "/api/players":
            players, err = load_players()
            self._json(
                200,
                {
                    "players": players,
                    "error": err,
                    "world_host_id": world_host_id(),
                    "bans": load_json_file(BANS_FILE, []),
                    "whitelist": load_json_file(WHITELIST_FILE, {"enabled": False, "ids": []}),
                },
            )
            return
        if path == "/api/player":
            pid = (parse_qs(u.query).get("id") or [""])[0]
            if not pid:
                self._json(400, {"ok": False, "error": "id required"})
                return
            fn = globals().get("player_detail")
            if not callable(fn):
                self._json(501, {"ok": False, "error": "extras not loaded"})
                return
            self._json(200, fn(pid))
            return
        if path == "/api/audit":
            fn = globals().get("read_audit")
            self._json(200, {"events": fn(80) if callable(fn) else []})
            return
        if path == "/api/backups":
            fn = globals().get("list_backups")
            self._json(200, {"backups": fn() if callable(fn) else []})
            return
        if path == "/api/settings":
            fn = globals().get("read_settings")
            self._json(200, fn() if callable(fn) else {"keys": []})
            return
        if path == "/api/config":
            fn = globals().get("read_admin_config")
            self._json(200, fn() if callable(fn) else {})
            return
        if path == "/api/social":
            fn = globals().get("social_intel")
            if not callable(fn):
                self._json(501, {"ok": False, "error": "extras not loaded"})
                return
            self._json(200, fn())
            return
        if path == "/api/world-objects":
            fn = globals().get("world_objects")
            kind = (parse_qs(u.query).get("kind") or ["all"])[0]
            if kind not in ("all", "bases", "vehicles", "orphans"):
                kind = "all"
            if not callable(fn):
                self._json(501, {"ok": False, "error": "extras not loaded"})
                return
            self._json(200, fn(kind))
            return
        if path == "/api/catalog":
            fn = globals().get("catalog")
            self._json(
                200,
                fn() if callable(fn) else {"items": [[x, x] for x in COMMON_ITEMS], "skills": []},
            )
            return
        if path == "/api/logs":
            kind = (parse_qs(u.query).get("kind") or ["survival"])[0]
            if kind not in ("survival", "overmap", "director", "gateway", "textrouter"):
                kind = "survival"
            self._json(200, {"text": pod_logs(kind)})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200_000:
            self._json(413, {"ok": False, "error": "too large"})
            return
        raw = self.rfile.read(n) if n else b"{}"
        if u.path == "/api/login":
            if not self._login_ok():
                self._json(429, {"ok": False, "error": "slow down"})
                return
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                body = {}
            if token_ok(str(body.get("token") or "")):
                extra = [("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=/" % (COOKIE, ensure_token()))]
                self._json(200, {"ok": True}, extra)
            else:
                self._json(401, {"ok": False, "error": "auth"})
            return
        if not self._auth():
            self._json(401, {"ok": False, "error": "auth"})
            return
        if u.path != "/api/action":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "bad json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"ok": False, "error": "bad json"})
            return
        try:
            result = do_action(body)
        except Exception as e:
            result = {"ok": False, "error": str(e)[:300]}
        fin = globals().get("finish_gm")
        if callable(fin) and isinstance(result, dict):
            result = fin(body, result)
        stamp = globals().get("stamp_op")
        if callable(stamp) and isinstance(result, dict) and result.get("ok") and not body.get("dry_run"):
            stamp(str(body.get("op") or ""), True)
        audit(str(body.get("op") or "action"), {"ok": result.get("ok"), "player_id": body.get("player_id"), "dry_run": bool(body.get("dry_run"))})
        self._json(200 if result.get("ok") else 400, result)


def _watchdog() -> None:
    while True:
        time.sleep(35)
        try:
            enforce_bans_and_whitelist()
            tick = globals().get("tick_extras")
            if callable(tick):
                tick()
        except Exception as e:
            print("watchdog: %s" % e, file=__import__("sys").stderr)


def bind_filebrowser(ip: str) -> None:
    n = ns()
    if not n:
        return
    code, out = run(["sudo", "ss", "-ltn"], timeout=8)
    if code == 0 and ":18888" in out:
        return
    data = kubectl_json(["get", "svc", "-n", n])
    if not isinstance(data, dict):
        return
    svc = ""
    port = 80
    for item in data.get("items") or []:
        name = ((item.get("metadata") or {}).get("name") or "")
        if "fb-" in name or "filebrowser" in name:
            svc = name
            ports = ((item.get("spec") or {}).get("ports") or [{}])
            port = int(ports[0].get("port") or 80)
            break
    if not svc:
        return
    subprocess.Popen(
        [
            "sudo",
            "kubectl",
            "-n",
            n,
            "port-forward",
            "--address",
            ip,
            "svc/" + svc,
            "18888:%d" % port,
        ],
        stdout=open(str(DUNE / "filebrowser-18888.log"), "ab", buffering=0),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def page_html() -> str:
    for p in (
        Path(__file__).resolve().with_name("dune-admin.html"),
        Path("/home/dune/.dune/bin/dune-admin.html"),
    ):
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return (
        "<!DOCTYPE html><title>Dune admin</title>"
        "<p>dune-admin.html is missing next to dune-admin.py</p>"
    )


def _bind_lib() -> None:
    candidates = (
        Path(__file__).resolve().with_name("dune-admin-lib.py"),
        Path("/home/dune/.dune/bin/dune-admin-lib.py"),
    )
    path = next((p for p in candidates if p.is_file()), None)
    if not path:
        print("dune-admin-lib.py missing; extra APIs disabled", file=sys.stderr)
        return
    spec = importlib.util.spec_from_file_location("dune_admin_lib", path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    host = sys.modules.get(__name__) or sys.modules.get("__main__")
    if host is None:
        print("dune-admin-lib bind skipped", file=sys.stderr)
        return
    mod.bind(host)


_bind_lib()


def main() -> None:
    ip = lan_ip()
    ensure_token()
    bind_filebrowser(ip)
    threading.Thread(target=_watchdog, name="dune-admin-watch", daemon=True).start()
    httpd = ThreadingHTTPServer((ip, LISTEN_PORT), Handler)
    print("dune-admin listening on http://%s:%d" % (ip, LISTEN_PORT), flush=True)
    print("token file %s (not printed)" % TOKEN_FILE, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
