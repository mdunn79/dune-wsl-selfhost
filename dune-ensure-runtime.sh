#!/usr/bin/env bash
# Bring k3s/CNI/BattleGroup back after a Windows or WSL restart.
# Safe to run on a healthy world: no k3s restart, no spec.stop patch, no map roll.
# Does not wipe operators. Does not download a depot.
set -euo pipefail

BG=/home/dune/.dune/bin/battlegroup

wait_k3s() {
  echo "Waiting for k3s..."
  local i
  for i in $(seq 1 60); do
    if sudo kubectl get --raw=/readyz >/dev/null 2>&1; then
      echo "k3s ready"
      return 0
    fi
    sleep 5
  done
  echo "ERROR: k3s did not become ready" >&2
  return 1
}

ensure_no_wan_node_ip() {
  local f changed=0
  for f in /etc/rancher/k3s/config.yaml.d/*.yaml /etc/rancher/k3s/config.yaml.d/*.yml; do
    [ -f "$f" ] || continue
    if grep -q 'node-external-ip' "$f"; then
      echo "removing $(basename "$f") (k3s node-external-ip wedges WSL; Unreal -ExternalAddress is the internet path)"
      sudo rm -f "$f"
      changed=1
    fi
  done
  if [ -f /etc/rancher/k3s/config.yaml ] && grep -q 'node-external-ip' /etc/rancher/k3s/config.yaml; then
    echo "stripping node-external-ip from k3s config.yaml"
    sudo sed -i '/node-external-ip/d' /etc/rancher/k3s/config.yaml
    changed=1
  fi
  if [ "$changed" -eq 1 ]; then
    sudo systemctl restart k3s
    wait_k3s
  else
    echo "k3s node-external-ip not set; skipping"
  fi
}

ensure_flannel() {
  if [ -s /run/flannel/subnet.env ]; then
    echo "flannel subnet.env present; skipping k3s restart"
    return 0
  fi
  echo "flannel subnet.env missing (typical after WSL restart); restarting k3s once"
  sudo systemctl restart k3s
  wait_k3s
  local i
  for i in $(seq 1 30); do
    if [ -s /run/flannel/subnet.env ]; then
      echo "flannel subnet.env restored"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: /run/flannel/subnet.env still missing after k3s restart" >&2
  return 1
}

world_ns() {
  sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null \
    | grep '^funcom-seabass-' | head -n1 || true
}

ensure_unstopped() {
  local ns bg stop
  ns="$(world_ns)"
  if [ -z "$ns" ]; then
    echo "No Funcom world namespace yet; skipping spec.stop repair"
    return 0
  fi
  bg="${ns#funcom-seabass-}"
  stop="$(sudo kubectl get battlegroup "$bg" -n "$ns" -o jsonpath='{.spec.stop}' 2>/dev/null || true)"
  case "$stop" in
    true|True|TRUE)
      echo "BattleGroup spec.stop=$stop; patching false (CLI start is a no-op after some WSL restarts)"
      sudo kubectl patch battlegroup "$bg" -n "$ns" --type merge -p '{"spec":{"stop":false}}'
      ;;
    *)
      echo "BattleGroup spec.stop=${stop:-unset}; leaving it"
      ;;
  esac
}

ensure_started_if_maps_missing() {
  local ns pods
  ns="$(world_ns)"
  [ -n "$ns" ] || return 0
  pods="$(sudo kubectl get pods -n "$ns" --no-headers 2>/dev/null | grep -E 'sg-survival|sg-overmap' || true)"
  if [ -n "$pods" ]; then
    echo "Map pods already present; not calling battlegroup start"
    return 0
  fi
  if [ ! -x "$BG" ]; then
    echo "battlegroup CLI missing; skip start"
    return 0
  fi
  echo "No Overmap/Survival pods; battlegroup start"
  "$BG" start || true
}

echo "=== dune-ensure-runtime ==="
wait_k3s
ensure_no_wan_node_ip
ensure_flannel
ensure_unstopped
ensure_started_if_maps_missing
echo "=== dune-ensure-runtime end ==="
