#!/usr/bin/env bash
# 5-minute local health: missing LAN join binds, dune-admin, and runtime only if map pods are gone.
# No Steam, depot, advertise, or FLS. Not Ready (pods still there) does not start maps.
set -uo pipefail
export HOME=/home/dune
RUNTIME=/home/dune/.dune/bin/dune-ensure-runtime.sh
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

k3s_up() { timeout 5 sudo kubectl get --raw=/readyz >/dev/null 2>&1; }

run_runtime() {
  if [ ! -x "$RUNTIME" ]; then
    echo "WARNING: $RUNTIME missing" >&2
    return 1
  fi
  echo "map pods missing or k3s down; running dune-ensure-runtime.sh (no Steam/advertise)"
  "$RUNTIME" || true
}

list_ns() {
  timeout 12 sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null
}

pick_ns() {
  printf '%s\n' "$1" | grep '^funcom-seabass-' | head -n1
}

if ! k3s_up; then
  run_runtime
  if ! k3s_up; then
    echo "k3s still not ready; skip binds"
    echo "=== dune-repair-health end ==="
    exit 0
  fi
fi

ns_list="$(list_ns)"
ns_rc=$?
if [ "$ns_rc" -ne 0 ]; then
  echo "kubectl get ns failed (rc $ns_rc); not treating world as missing"
  echo "=== dune-repair-health end ==="
  exit 0
fi
NS="$(pick_ns "$ns_list")"
if [ -z "$NS" ]; then
  run_runtime
  ns_list="$(list_ns)"
  ns_rc=$?
  NS=""
  [ "$ns_rc" -eq 0 ] && NS="$(pick_ns "$ns_list")"
  if [ -z "$NS" ]; then
    echo "no funcom-seabass namespace after runtime restore; skip binds"
    echo "=== dune-repair-health end ==="
    exit 0
  fi
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

list_pods() {
  timeout 12 sudo kubectl get pods -n "$NS" --no-headers 2>/dev/null
}

pods="$(list_pods)"
pods_rc=$?
if [ "$pods_rc" -ne 0 ]; then
  echo "kubectl get pods failed (rc $pods_rc); not treating maps as missing"
  pods=""
else
  surv_any="$(printf '%s\n' "$pods" | awk '/sg-survival/ {print $1; exit}')"
  over_any="$(printf '%s\n' "$pods" | awk '/sg-overmap/ {print $1; exit}')"
  if [ -z "$surv_any" ] && [ -z "$over_any" ]; then
    run_runtime
    pods="$(list_pods)"
    pods_rc=$?
    [ "$pods_rc" -ne 0 ] && pods=""
  fi
fi

surv="$(printf '%s\n' "$pods" | awk '/sg-survival-1/ && $3=="Running" && $2=="1/1" {print $1; exit}')"
over="$(printf '%s\n' "$pods" | awk '/sg-overmap/ && $3=="Running" && $2=="1/1" {print $1; exit}')"
if [ "$pods_rc" -eq 0 ]; then
  if [ -n "$surv" ] && [ -n "$over" ]; then
    echo "maps Ready (Survival+Overmap Running 1/1)"
  else
    echo "maps not Running 1/1; not calling battlegroup start (hourly maintain if they stay down)"
  fi
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
