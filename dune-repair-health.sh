#!/usr/bin/env bash
# 5-minute local health: missing LAN join binds + dune-admin.
# No Steam, depot, advertise, FLS, hosts, battlegroup start, or k3s restart.
set -uo pipefail
export HOME=/home/dune
echo "=== dune-repair-health begin ==="

if pgrep -f '/home/dune/.dune/bin/dune-maintain.sh' >/dev/null 2>&1; then
  echo "maintain running; skip"
  echo "=== dune-repair-health end ==="
  exit 0
fi

if systemctl is-active --quiet dune-admin.service; then
  echo "dune-admin active"
else
  echo "dune-admin down; starting"
  sudo systemctl start dune-admin.service && echo "dune-admin started" || echo "WARNING: dune-admin start failed" >&2
fi

NS="$(timeout 12 sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
if [ -z "$NS" ]; then
  echo "k3s/namespace not answering; skip binds (hourly maintain restores runtime)"
  echo "=== dune-repair-health end ==="
  exit 0
fi

BG="${NS#funcom-seabass-}"
LAN_IP="${DUNE_LAN_IP:-}"
[ -z "$LAN_IP" ] && [ -s /home/dune/.dune/lan-ip.conf ] && LAN_IP="$(tr -d '[:space:]' < /home/dune/.dune/lan-ip.conf)"
[ -z "$LAN_IP" ] && LAN_IP="$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
if [ -z "$LAN_IP" ]; then
  echo "WARNING: no LAN IP; skip binds" >&2
  echo "=== dune-repair-health end ==="
  exit 0
fi

pods="$(timeout 12 sudo kubectl get pods -n "$NS" --no-headers 2>/dev/null || true)"
surv="$(printf '%s\n' "$pods" | awk '/sg-survival-1/ && $3=="Running" && $2=="1/1" {print $1; exit}')"
over="$(printf '%s\n' "$pods" | awk '/sg-overmap/ && $3=="Running" && $2=="1/1" {print $1; exit}')"
if [ -n "$surv" ] && [ -n "$over" ]; then
  echo "maps Ready (Survival+Overmap Running 1/1)"
else
  echo "maps not Running 1/1; not starting battlegroup"
fi

listen() { sudo ss -ltn | grep -qE ":$1\\b"; }

rebind() {
  local port="$1" spec="$2" log="$3" pat="$4" name="$5"
  if listen "$port"; then
    echo "already listening ${LAN_IP}:$port ($name)"
    return 0
  fi
  echo "rebind ${LAN_IP}:$port"
  sudo pkill -f "$pat" >/dev/null 2>&1 || true
  sleep 1
  # shellcheck disable=SC2086
  nohup sudo kubectl -n "$NS" port-forward --address "$LAN_IP" $spec >"$log" 2>&1 &
  sleep 2
  if listen "$port"; then
    echo "$name listening on ${LAN_IP}:$port"
  else
    echo "WARNING: ${LAN_IP}:$port is not listening yet" >&2
    tail -n 8 "$log" >&2 || true
  fi
}

rebind 31982 "svc/${BG}-mq-game-svc 31982:5672" /home/dune/.dune/rmq-31982.log "port-forward.*${BG}-mq-game-svc.*31982" "rmq-join"
rebind 31519 "svc/${BG}-bgd-svc 31519:11717" /home/dune/.dune/director.log "port-forward.*${BG}-bgd-svc.*31519" "director"
if listen 18888; then
  echo "already listening ${LAN_IP}:18888 (file browser)"
else
  echo "WARNING: ${LAN_IP}:18888 not listening (no file-browser Service on this stack; hourly join bind is a no-op too)"
fi

echo "=== dune-repair-health end ==="
exit 0
