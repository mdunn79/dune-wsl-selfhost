#!/usr/bin/env bash
# Ensure the battlegroup is running and only roll maps when Steam has a newer depot.
# Called from Windows Restart-DuneBattlegroup.ps1. Does not wipe operators.
set -euo pipefail

export PYTHONUNBUFFERED=1
export HOME=/home/dune

BG=/home/dune/.dune/bin/battlegroup
JOIN=/home/dune/.dune/bin/dune-ensure-join.sh
UPDATE_LOG=/home/dune/.dune/last-update.log
MANIFEST=/home/dune/.dune/download/steamapps/appmanifest_4754530.acf
APPINFO=/home/dune/.dune/last-appinfo.txt
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-1200}"
APPID=4754530

resolve_steamcmd() {
  if command -v steamcmd >/dev/null 2>&1; then
    command -v steamcmd
  elif [ -x /home/dune/.local/bin/steamcmd ]; then
    echo /home/dune/.local/bin/steamcmd
  elif [ -x /home/dune/Steam/steamcmd.sh ]; then
    echo /home/dune/Steam/steamcmd.sh
  else
    echo ""
  fi
}

local_steam_buildid() {
  if [ ! -f "$MANIFEST" ]; then
    echo ""
    return
  fi
  python3 - "$MANIFEST" <<'PY'
import re, sys
t = open(sys.argv[1], errors="replace").read()
m = re.search(r'"buildid"\s+"(\d+)"', t)
print(m.group(1) if m else "")
PY
}

steam_public_buildid() {
  local steamcmd
  steamcmd="$(resolve_steamcmd)"
  if [ -z "$steamcmd" ]; then
    echo ""
    return 1
  fi
  # Query only: never +app_update. Does not download the depot or roll maps.
  "$steamcmd" +@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 \
    +login anonymous +app_info_update 1 +app_info_print "$APPID" +quit \
    > "$APPINFO" 2>&1 || true
  python3 - "$APPINFO" <<'PY'
import re, sys
t = open(sys.argv[1], errors="replace").read()
m = re.search(r'"branches"\s*\{\s*"public"\s*\{[^}]*?"buildid"\s+"(\d+)"', t, re.S)
print(m.group(1) if m else "")
PY
}

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

operators_answer() {
  sudo kubectl get battlegroup -A >/dev/null 2>&1
}

recover_operators_if_stale() {
  if operators_answer; then
    echo "Operators answering (not recovering)"
    return 0
  fi
  echo "Operators not answering; clearing stale leases and restarting operator pods"
  sudo kubectl delete lease -n funcom-operators --all --ignore-not-found
  sudo kubectl delete pod -n funcom-operators --all --force --grace-period=0 --ignore-not-found
  local i
  for i in $(seq 1 40); do
    if sudo kubectl wait --for=condition=Available -n funcom-operators --all=true deployment --timeout=15s >/dev/null 2>&1; then
      echo "Operators available"
      return 0
    fi
    sleep 5
  done
  echo "ERROR: Funcom operators did not become Available" >&2
  sudo kubectl get pods -n funcom-operators || true
  return 1
}

maps_ready() {
  local status
  status="$("$BG" status 2>/dev/null || true)"
  echo "$status" | grep -qiE '[[:space:]](Modifying|Suspended)[[:space:]]' && return 1
  echo "$status" | grep -qE 'Healthy' \
    && echo "$status" | grep -qE 'Overmap[[:space:]]+Running[[:space:]]+true' \
    && echo "$status" | grep -qE 'Survival_1[[:space:]]+Running[[:space:]]+true'
}

wait_maps_ready() {
  echo "Waiting up to ${READY_TIMEOUT_SEC}s for Overmap + Survival Ready (ignore stale Running during Modifying)..."
  local elapsed=0 stable=0
  local need="${READY_STABLE_CHECKS:-3}"
  while [ "$elapsed" -lt "$READY_TIMEOUT_SEC" ]; do
    "$BG" status || true
    if maps_ready; then
      stable=$((stable + 1))
      echo "Ready streak $stable/$need"
      if [ "$stable" -ge "$need" ]; then
        echo "Maps Ready"
        return 0
      fi
    else
      stable=0
    fi
    sleep 15
    elapsed=$((elapsed + 15))
  done
  echo "ERROR: maps not Ready within ${READY_TIMEOUT_SEC}s" >&2
  "$BG" status || true
  return 1
}

run_battlegroup_update() {
  # Funcom prompts "Retry? [Y/N]" after two SteamCMD failures. A scheduled job
  # must never sit on that prompt — close stdin so read gets EOF and exits.
  echo "Running battlegroup update (SteamCMD app $APPID)..."
  set +e
  set +o pipefail
  "$BG" update < /dev/null 2>&1 | tee "$UPDATE_LOG"
  local rc=${PIPESTATUS[0]}
  set -e
  set -o pipefail
  return "$rc"
}

update_looks_applied() {
  grep -q 'Finished updating battlegroup to version' "$UPDATE_LOG"
}

steam_failed() {
  grep -qiE 'Steam download failed|Error! App .4754530. state is 0x6' "$UPDATE_LOG"
}

clear_stale_steam_manifest() {
  echo "Clearing stale Steam appmanifest so the next depot can download (old manifest Access Denied)."
  rm -f "$MANIFEST"
}

apply_depot_update() {
  local update_rc=0
  run_battlegroup_update || update_rc=$?
  if update_looks_applied; then
    echo "Patch applied (Funcom exit $update_rc; symlink 'File exists' is expected)"
    return 0
  fi
  if steam_failed; then
    echo "SteamCMD failed on first pass (exit $update_rc). Retrying once after dropping the stale manifest."
    clear_stale_steam_manifest
    update_rc=0
    run_battlegroup_update || update_rc=$?
    if update_looks_applied; then
      echo "Patch applied on retry (Funcom exit $update_rc)"
      return 0
    fi
    echo "ERROR: Steam/image update failed after retry (exit $update_rc)" >&2
    tail -n 40 "$UPDATE_LOG" >&2 || true
    return 1
  fi
  if [ "$update_rc" -eq 0 ]; then
    echo "Update command exited 0"
    return 0
  fi
  echo "ERROR: battlegroup update failed (exit $update_rc) without a finished-version line" >&2
  tail -n 40 "$UPDATE_LOG" >&2 || true
  return 1
}

echo "=== dune-maintain begin ==="

wait_k3s
recover_operators_if_stale

status="$("$BG" status 2>/dev/null || true)"
echo "$status"

rolled=0
if echo "$status" | grep -qiE 'Suspended|Stopped' || ! maps_ready; then
  echo "Battlegroup not Ready; starting (no depot download yet)"
  "$BG" start
  rolled=1
fi

echo "=== Steam public build vs installed depot (query only) ==="
local_id="$(local_steam_buildid)"
remote_id="$(steam_public_buildid || true)"
echo "local_buildid ${local_id:-MISSING}"
echo "steam_public_buildid ${remote_id:-UNKNOWN}"

need_update=0
if [ -z "$local_id" ]; then
  echo "No local appmanifest; depot apply is required"
  need_update=1
elif [ -z "$remote_id" ]; then
  echo "Steam query did not return a public buildid; not taking maps down"
  tail -n 20 "$APPINFO" >&2 || true
elif [ "$local_id" != "$remote_id" ]; then
  echo "Newer Steam depot available ($local_id -> $remote_id); maps will roll"
  need_update=1
else
  echo "Already on Steam public build $local_id; skipping battlegroup update"
fi

if [ "$need_update" -eq 1 ]; then
  echo "=== SteamCMD + apply latest depot (battlegroup update) ==="
  apply_depot_update
  rolled=1
fi

if [ "$rolled" -eq 1 ]; then
  echo "=== Ensure battlegroup is started after a start/update ==="
  "$BG" start
  wait_maps_ready
  echo "=== Refresh /etc/hosts and rebind LAN join/director ==="
  REFRESH_FORWARDS=1 "$JOIN"
  if ! maps_ready; then
    echo "=== wait maps Ready after FLS DNS rewrite (Survival/Overmap restart once) ==="
    wait_maps_ready
    "$JOIN"
  fi
else
  echo "=== Maps already Ready on current depot; bind join ports only if missing ==="
  "$JOIN"
fi

echo "=== dune-maintain end ==="
"$BG" status
if [ -f "$UPDATE_LOG" ] && [ "$need_update" -eq 1 ]; then
  echo "Image / depot version from last update:"
  grep -E 'Downloaded version|Finished updating battlegroup to version|Success! App' "$UPDATE_LOG" | tail -n 8 || true
fi
