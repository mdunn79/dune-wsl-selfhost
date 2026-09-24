#!/usr/bin/env bash
# After the battlegroup is up: refresh /etc/hosts and bind LAN TCP 31982 (join RMQ).
set -euo pipefail
NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
if [ -z "$NS" ]; then
  echo "ERROR: no funcom-seabass-* namespace" >&2
  exit 1
fi
BG="${NS#funcom-seabass-}"
SVC="${BG}-mq-game-svc"
BGD="${BG}-bgd-svc"
LAN_IP="$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
if [ -z "$LAN_IP" ]; then
  LAN_IP="${DUNE_LAN_IP:-}"
fi
if [ -z "$LAN_IP" ]; then
  echo "ERROR: could not detect LAN IP; set DUNE_LAN_IP" >&2
  exit 1
fi

/home/dune/.dune/bin/apply-k8s-hosts.sh
if [ -x /home/dune/.dune/bin/dune-fix-fls-dns.sh ]; then
  /home/dune/.dune/bin/dune-fix-fls-dns.sh || true
fi

if [ "${REFRESH_FORWARDS:-0}" = "1" ]; then
  sudo pkill -f "port-forward.*${SVC}.*31982" >/dev/null 2>&1 || true
  sudo pkill -f "port-forward.*${BGD}.*31519" >/dev/null 2>&1 || true
  sleep 1
fi

if sudo ss -ltn | grep -qE ':31982\b'; then
  echo "already listening ${LAN_IP}:31982 (rmq-join)"
else
  sudo pkill -f "port-forward.*${SVC}.*31982" >/dev/null 2>&1 || true
  sleep 1
  nohup sudo kubectl -n "$NS" port-forward --address "$LAN_IP" "svc/${SVC}" 31982:5672 \
    >/home/dune/.dune/rmq-31982.log 2>&1 &
  sleep 2
  if sudo ss -ltn | grep -qE ':31982\b'; then
    echo "RMQ join port listening on ${LAN_IP}:31982"
  else
    echo "WARNING: ${LAN_IP}:31982 is not listening yet" >&2
    tail -n 20 /home/dune/.dune/rmq-31982.log >&2 || true
    exit 1
  fi
fi

if sudo ss -ltn | grep -qE ':31519\b'; then
  echo "already listening ${LAN_IP}:31519 (director)"
else
  bound=0
  for i in 1 2 3 4 5 6; do
    sudo pkill -f "port-forward.*${BGD}.*31519" >/dev/null 2>&1 || true
    nohup sudo kubectl -n "$NS" port-forward --address "$LAN_IP" "svc/${BGD}" 31519:11717 \
      >/home/dune/.dune/director.log 2>&1 &
    sleep 3
    if sudo ss -ltn | grep -qE ':31519\b'; then
      echo "Director listening on ${LAN_IP}:31519"
      bound=1
      break
    fi
    echo "director 31519 not up yet ($i/6)"
  done
  if [ "$bound" -ne 1 ]; then
    echo "WARNING: ${LAN_IP}:31519 (director) is not listening" >&2
    tail -n 15 /home/dune/.dune/director.log >&2 || true
  fi
fi
