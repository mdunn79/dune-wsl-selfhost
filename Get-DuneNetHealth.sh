#!/usr/bin/env bash
# Read-only. Objective rubberband / join-path signals from Hagga logs.
# Does not print tokens, player ids, or JWT.
set +e
SINCE="${SINCE:-15m}"
WATCH="${WATCH:-0}"
NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
if [ -z "$NS" ]; then
  echo "ERROR: no funcom-seabass-* namespace"
  exit 1
fi
POD="$(sudo kubectl get pods -n "$NS" --no-headers -o custom-columns=NAME:.metadata.name | grep sg-survival | head -n1)"
if [ -z "$POD" ]; then
  echo "ERROR: no Survival pod"
  exit 1
fi

PUB="$(/home/dune/.dune/bin/dune-set-advertise-ip.sh --status 2>/dev/null | awk -F= '/^HOST_DATACENTER=/{print $2; exit}')"
LAN=""
if [ -s /home/dune/.dune/lan-ip.conf ]; then
  LAN="$(tr -d '[:space:]' < /home/dune/.dune/lan-ip.conf)"
fi
[ -n "$LAN" ] || LAN="$(/home/dune/.dune/bin/dune-set-advertise-ip.sh --status 2>/dev/null | awk -F= '/^lan_bind=/{print $2; exit}')"

classify() {
  local ip="$1"
  if [ -n "$PUB" ] && [ "$ip" = "$PUB" ]; then
    echo "hairpin-or-self-wan"
  elif echo "$ip" | grep -qE '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)'; then
    echo "lan"
  else
    echo "internet"
  fi
}

dump_window() {
  local label="$1" since="$2"
  local logs
  logs="$(sudo kubectl logs -n "$NS" "$POD" --since="$since" 2>/dev/null || true)"
  local expired
  expired="$(printf '%s\n' "$logs" | grep -c 'ServerMove: TimeStamp expired' || true)"
  echo "=== $label (since $since) ==="
  echo "timestamp_expired_count=$expired"
  printf '%s\n' "$logs" | python3 -c '
import re,sys,collections
text=sys.stdin.read()
deltas=[]
pat=re.compile(r"TimeStamp expired:\s*([0-9.]+),\s*CurrentTimeStamp:\s*([0-9.]+)")
for a,b in pat.findall(text):
    try:
        d=float(b)-float(a)
        if d>=0: deltas.append(d)
    except ValueError:
        pass
if deltas:
    deltas.sort()
    print("expired_delay_sec min=%.3f median=%.3f max=%.3f n=%d" % (
        deltas[0], deltas[len(deltas)//2], deltas[-1], len(deltas)))
else:
    print("expired_delay_sec n=0")
addrs=collections.OrderedDict()
for m in re.finditer(r"RemoteAddr:\s*([0-9.]+):(\d+)", text):
    addrs[m.group(1)]=m.group(2)
for ip,port in addrs.items():
    print("remote %s (last src port %s)" % (ip, port))
' 
  printf '%s\n' "$logs" | grep -E 'RemoteAddr:' | grep -oE 'RemoteAddr: [0-9.]+' | awk '{print $2}' | sort | uniq -c | while read -r c ip; do
    echo "remote_count $c $ip $(classify "$ip")"
  done
}

echo "pod=$POD advertise=${PUB:-unknown} lan_bind=${LAN:-unknown}"
echo "hairpin = client RemoteAddr equals advertise/public IP"
echo "lan     = RemoteAddr is RFC1918 (redirect POC working, or listing was LAN)"
echo "internet= some other public IP"
echo
dump_window "recent" "$SINCE"
echo
dump_window "last_2m" "2m"
echo
echo "=== client RemoteAddr (since 60m; UniqueId stripped) ==="
sudo kubectl logs -n "$NS" "$POD" --since=60m 2>/dev/null \
  | grep -oE 'RemoteAddr: [0-9.]+' | awk '{print $2}' | sort | uniq -c \
  | while read -r c ip; do
      echo "remote_count $c $ip $(classify "$ip")"
    done
if ! sudo kubectl logs -n "$NS" "$POD" --since=60m 2>/dev/null | grep -q 'RemoteAddr:'; then
  echo "no RemoteAddr lines (nobody joined in this window, or logs rotated)"
fi
echo
echo "=== survival recv-q (UDP 7778/7889) ==="
sudo ss -lun | grep -E ':7778|:7889' || true

if [ "$WATCH" != "0" ]; then
  echo
  echo "=== watch ${WATCH}s (counts per ~10s slice) ==="
  end=$((SECONDS + WATCH))
  while [ "$SECONDS" -lt "$end" ]; do
    n="$(sudo kubectl logs -n "$NS" "$POD" --since=12s 2>/dev/null | grep -c 'ServerMove: TimeStamp expired' || true)"
    echo "$(date +%H:%M:%S) expired_last_12s=$n"
    sleep 10
  done
fi
