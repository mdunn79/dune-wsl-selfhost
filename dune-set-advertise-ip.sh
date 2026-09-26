#!/usr/bin/env bash
# Point Funcom's directory AND Unreal's client UDP address at the advertise IPv4.
# Bind/listen stays the LAN address. Do not set k3s node-external-ip to a WAN
# address: the embedded agent then dials WAN:6443 and breaks behind NAT.
#
# Usage:
#   dune-set-advertise-ip.sh                 # public mode -> ipify; else settings.conf / LAN
#   dune-set-advertise-ip.sh auto            # look up current public IPv4
#   dune-set-advertise-ip.sh 1.2.3.4         # explicit IPv4
#   dune-set-advertise-ip.sh --status        # print bind vs advertise (no secrets)
set -euo pipefail

lan_ip() {
  if [ -n "${DUNE_LAN_IP:-}" ]; then
    printf '%s\n' "$DUNE_LAN_IP"
    return
  fi
  ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1
}

lookup_public_ip() {
  python3 - <<'PY'
import urllib.request
for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
    try:
        ip = urllib.request.urlopen(url, timeout=8).read().decode().strip()
        if ip.count(".") == 3 and not ip.startswith(("10.", "127.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.")):
            print(ip)
            break
    except Exception:
        pass
PY
}

ns_and_bg() {
  NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
  if [ -z "$NS" ]; then
    echo "ERROR: no funcom-seabass-* namespace" >&2
    return 1
  fi
  BG="${NS#funcom-seabass-}"
}

print_status() {
  ns_and_bg || return 1
  local lan settings hostdc ext_args mh run_ext
  lan="$(lan_ip)"
  settings="$(awk 'NF{p=$0} END{print p}' /home/dune/.dune/settings.conf 2>/dev/null || true)"
  hostdc="$(
    sudo kubectl get battlegroup "$BG" -n "$NS" -o json | python3 -c '
import json,sys
bg=json.load(sys.stdin)
vals=set()
def walk(n):
    if isinstance(n, dict):
        for item in n.get("envVars") or []:
            if isinstance(item, dict) and item.get("name")=="HOST_DATACENTER_IP_ADDRESS":
                vals.add(item.get("value") or "")
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(bg.get("spec",{}))
print(",".join(sorted(vals)) if vals else "")
'
  )"
  ext_args="$(
    sudo kubectl get battlegroup "$BG" -n "$NS" -o json | python3 -c '
import json,sys
bg=json.load(sys.stdin)
vals=set()
def walk(n):
    if isinstance(n, dict):
        args=n.get("arguments")
        if isinstance(args, list) and args and isinstance(args[0], str):
            for a in args:
                if isinstance(a, str) and a.startswith("-ExternalAddress="):
                    vals.add(a.split("=",1)[1])
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(bg.get("spec",{}))
print(",".join(sorted(vals)) if vals else "(none)")
'
  )"
  mh="$(tr '\0' '\n' < /proc/$(pgrep -n DuneSandboxServ 2>/dev/null || echo 1)/cmdline 2>/dev/null | grep -E '^-MultiHome=' | head -n1 | cut -d= -f2 || true)"
  run_ext="$(tr '\0' '\n' < /proc/$(pgrep -n DuneSandboxServ 2>/dev/null || echo 1)/cmdline 2>/dev/null | grep -E '^-ExternalAddress=' | head -n1 | cut -d= -f2 || true)"
  echo "lan_bind=${lan:-unknown}"
  echo "settings.conf=${settings:-empty}"
  echo "HOST_DATACENTER=${hostdc:-unknown}"
  echo "spec_ExternalAddress=${ext_args}"
  echo "running_MultiHome=${mh:-not-running}"
  echo "running_ExternalAddress=${run_ext:-none}"
  echo "choice=$(tr -d '\n' < /home/dune/.dune/battlegroup-ip.conf 2>/dev/null || echo missing)"
}

if [ "${1:-}" = "--status" ] || [ "${1:-}" = "status" ]; then
  print_status
  exit 0
fi

LAN="$(lan_ip)"
if [ -z "$LAN" ]; then
  echo "ERROR: could not detect LAN IP; set DUNE_LAN_IP" >&2
  exit 1
fi

CHOICE="$(tr -d '[:space:]' < /home/dune/.dune/battlegroup-ip.conf 2>/dev/null || true)"
ARG="${1:-${DUNE_ADVERTISE_IP:-}}"

if [ -z "$ARG" ]; then
  if [ "$CHOICE" = "public" ] || [ "$CHOICE" = "auto" ]; then
    ARG="auto"
  else
    ARG="$(awk 'NF{p=$0} END{print p}' /home/dune/.dune/settings.conf 2>/dev/null || true)"
    [ -n "$ARG" ] || ARG="$LAN"
  fi
fi

if [ "$ARG" = "auto" ] || [ "$ARG" = "public" ]; then
  ARG="$(lookup_public_ip)"
  if [ -z "$ARG" ]; then
    echo "ERROR: could not look up public IPv4" >&2
    exit 1
  fi
  CHOICE="public"
elif [ "$ARG" = "$LAN" ]; then
  CHOICE="private"
else
  CHOICE="public"
fi

if ! printf '%s' "$ARG" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: advertise IP must be dotted IPv4 (got '$ARG')" >&2
  exit 1
fi

mkdir -p /home/dune/.dune
printf '%s\n' "$CHOICE" > /home/dune/.dune/battlegroup-ip.conf
printf '\n\n\n%s\n' "$ARG" > /home/dune/.dune/settings.conf
chown dune:dune /home/dune/.dune/battlegroup-ip.conf /home/dune/.dune/settings.conf 2>/dev/null || true

ns_and_bg || exit 1

PATCH="$(
  sudo kubectl get battlegroup "$BG" -n "$NS" -o json \
    | DUNE_ADVERTISE_IP="$ARG" DUNE_LAN_IP="$LAN" python3 -c '
import json,os,sys
bg=json.load(sys.stdin)
player_ip=os.environ["DUNE_ADVERTISE_IP"]
lan_ip=os.environ["DUNE_LAN_IP"]
want_ext = player_ip != lan_ip
ext_arg = "-ExternalAddress=" + player_ip
ops=[]
def esc(part):
    return str(part).replace("~","~0").replace("/","~1")
def walk(node, path):
    if isinstance(node, dict):
        envs=node.get("envVars")
        if isinstance(envs, list):
            for i,item in enumerate(envs):
                if isinstance(item, dict) and item.get("name")=="HOST_DATACENTER_IP_ADDRESS":
                    if item.get("value") != player_ip:
                        ops.append({
                            "op": "replace" if "value" in item else "add",
                            "path": "/" + "/".join(esc(p) for p in path+["envVars", i, "value"]),
                            "value": player_ip,
                        })
        args=node.get("arguments")
        if isinstance(args, list) and args and isinstance(args[0], str) and any(
            isinstance(a, str) and (a.startswith("-FarmRegion=") or a.startswith("-RMQGameTlsEnabled") or a.startswith("-ExternalAddress="))
            for a in args
        ):
            new=[]
            for a in args:
                if isinstance(a, str) and a.startswith("-ExternalAddress="):
                    continue
                new.append(a)
            if want_ext:
                new.append(ext_arg)
            if new != args:
                ops.append({
                    "op": "replace",
                    "path": "/" + "/".join(esc(p) for p in path+["arguments"]),
                    "value": new,
                })
        for key, value in node.items():
            walk(value, path+[key])
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk(value, path+[i])
walk(bg.get("spec", {}), ["spec"])
print(json.dumps(ops))
'
)"

python3 - <<PY
from pathlib import Path
import re, os
ip = os.environ.get("DUNE_ADVERTISE_IP", "$ARG")
lan = os.environ.get("DUNE_LAN_IP", "$LAN")
want_ext = ip != lan
pat = re.compile(r"(name:\s*HOST_DATACENTER_IP_ADDRESS\s*\n\s*value:\s*)(\S+)")
ext_line = "          - -ExternalAddress=" + ip
for path in Path("/home/dune/.dune").glob("sh-*.yaml"):
    if "secret" in path.name:
        continue
    text = path.read_text()
    updated, n = pat.subn(r"\g<1>" + ip, text)
    lines = updated.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"\s*-\s*-ExternalAddress=", line):
            i += 1
            continue
        out.append(line)
        if want_ext and re.match(r"\s*-\s*-RMQGameTlsEnabled=", line):
            nxt = lines[i+1] if i+1 < len(lines) else ""
            if not re.match(r"\s*-\s*-ExternalAddress=", nxt):
                indent = re.match(r"^(\s*)", line).group(1)
                out.append(indent + "- -ExternalAddress=" + ip)
        i += 1
    new = "\n".join(out) + ("\n" if updated.endswith("\n") else "")
    if new != text:
        path.write_text(new)
        print("patched disk yaml " + str(path.name))
PY

changed=no
if [ "$PATCH" != "[]" ]; then
  sudo kubectl patch battlegroup "$BG" -n "$NS" --type=json -p "$PATCH" >/dev/null
  changed=yes
  echo "patched live BattleGroup listing + Unreal ExternalAddress"
else
  echo "BattleGroup advertise already $ARG (bind $LAN); skipping patch"
fi

echo "advertise=$ARG bind=$LAN choice=$CHOICE changed=$changed"
if [ "$changed" = "yes" ]; then
  echo "Maps will roll. Wait until Survival is Running / true, then bind join ports."
fi
