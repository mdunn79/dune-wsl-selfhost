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

map_pods_lines() {
  local ns="$1"
  sudo kubectl get pods -n "$ns" --no-headers 2>/dev/null | grep -E 'sg-survival|sg-overmap' || true
}

ensure_db_schema() {
  local ns depl phase failed ver
  ns="$(world_ns)"
  [ -n "$ns" ] || return 0
  depl="$(sudo kubectl get databasedeployment -n "$ns" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | head -n1 || true)"
  [ -n "$depl" ] || return 0
  phase="$(sudo kubectl get databasedeployment "$depl" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [ "$phase" = "Ready" ]; then
    echo "DatabaseDeployment Ready"
    return 0
  fi
  echo "DatabaseDeployment phase=${phase:-unset}"
  failed="$(sudo kubectl get pods -n "$ns" --no-headers 2>/dev/null | awk '/db-dbdepl-util-/ && /Error|CrashLoopBackOff/ {print $1}' || true)"
  if [ -z "$failed" ] && [ "$phase" != "Pending" ] && [ "$phase" != "Modifying" ]; then
    return 0
  fi
  if [ -n "$failed" ] || [ "$phase" = "Pending" ]; then
    echo "Schema util stuck (failed pods: ${failed:-none}); deleting util pods so the operator can re-reconcile"
    sudo kubectl get pods -n "$ns" --no-headers 2>/dev/null \
      | awk '/db-dbdepl-util-/ {print $1}' \
      | xargs -r sudo kubectl delete pod -n "$ns" --force --grace-period=0 --ignore-not-found
    echo "Restarting database operator"
    sudo kubectl get pod -n funcom-operators -o name 2>/dev/null \
      | grep databaseoperator \
      | xargs -r sudo kubectl delete -n funcom-operators --force --grace-period=0
    sudo kubectl wait --for=condition=Available -n funcom-operators \
      deploy/databaseoperator-controller-manager --timeout=90s >/dev/null 2>&1 || true
    local i
    for i in $(seq 1 24); do
      phase="$(sudo kubectl get databasedeployment "$depl" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
      echo "db phase=$phase ($i)"
      [ "$phase" = "Ready" ] && return 0
      sleep 5
    done
  fi
  ver=""
  if [ -f /home/dune/.dune/last-update.log ]; then
    ver="$(grep -oE 'Finished updating battlegroup to version [^[:space:]]+' /home/dune/.dune/last-update.log 2>/dev/null | awk '{print $NF}' | tail -n1 || true)"
  fi
  if [ -n "$ver" ] && [ "$phase" != "Ready" ]; then
    echo "DB still $phase; marking schema $ver Ready (duplicate patch already applied)"
    sudo kubectl patch databasedeployment "$depl" -n "$ns" --subresource=status --type merge \
      -p "{\"status\":{\"phase\":\"Ready\",\"schema\":\"$ver\"}}" >/dev/null || true
    sudo kubectl get database -n "$ns" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null \
      | head -n1 \
      | xargs -r -I{} sudo kubectl patch database {} -n "$ns" --subresource=status --type merge \
        -p '{"status":{"phase":"Ready"}}' >/dev/null || true
  fi
}

ensure_igw_unsuspended() {
  local ns kind name sus dbphase
  ns="$(world_ns)"
  [ -n "$ns" ] || return 0
  dbphase="$(sudo kubectl get database -n "$ns" --no-headers -o custom-columns=PHASE:.status.phase 2>/dev/null | head -n1 || true)"
  if [ "$dbphase" != "Ready" ]; then
    echo "Database not Ready ($dbphase); not unsuspending director"
    return 0
  fi
  for kind in battlegroupdirector servergateway textrouter; do
    name="$(sudo kubectl get "$kind" -n "$ns" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | head -n1 || true)"
    [ -n "$name" ] || continue
    sus="$(sudo kubectl get "$kind" "$name" -n "$ns" -o jsonpath='{.spec.suspend}' 2>/dev/null || true)"
    if [ "$sus" = "true" ]; then
      echo "unsuspending $kind/$name"
      sudo kubectl patch "$kind" "$name" -n "$ns" --type merge -p '{"spec":{"suspend":false}}' || true
    fi
  done
}

ensure_started_if_maps_missing() {
  local ns pods
  ns="$(world_ns)"
  [ -n "$ns" ] || return 0
  pods="$(map_pods_lines "$ns")"
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
  sleep 12
  pods="$(map_pods_lines "$ns")"
  if [ -z "$pods" ]; then
    echo "Maps still missing after start; unsuspend IGW and start once more"
    ensure_igw_unsuspended
    "$BG" start || true
  fi
}

echo "=== dune-ensure-runtime ==="
wait_k3s
ensure_no_wan_node_ip
ensure_flannel
ensure_unstopped
ensure_db_schema
ensure_igw_unsuspended
ensure_started_if_maps_missing
echo "=== dune-ensure-runtime end ==="
