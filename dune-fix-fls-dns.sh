#!/usr/bin/env bash
# Make hostNetwork Unreal able to resolve Funcom FLS (HP3).
# 1) CoreDNS: serve/forward sb-retail.fls.funcom.com via 8.8.8.8
# 2) Game sandboxes: nameserver 8.8.8.8 and ndots:1 (c-ares ignores /etc/hosts;
#    ClusterFirstWithHostNet ndots:5 times out on WSL's DNS tunnel).
set -euo pipefail
NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
SETUP_SRC="${SETUP_SRC:-}"
RESOLV_BODY=$'nameserver 8.8.8.8\nnameserver 1.1.1.1\noptions ndots:1\n'

apply_coredns() {
  local src="" base
  base="$(cd "$(dirname "$0")" && pwd)"
  for c in \
    "${SETUP_SRC:-}/coredns-custom.yaml" \
    "$base/coredns-custom.yaml" \
    /home/dune/.dune/bin/coredns-custom.yaml
  do
    if [ -n "$c" ] && [ -f "$c" ]; then src="$c"; break; fi
  done
  if [ -z "$src" ]; then
    echo "WARNING: coredns-custom.yaml not found" >&2
    return 0
  fi
  sed 's/\r$//' "$src" | sudo kubectl apply -f -
  sudo mkdir -p /var/lib/rancher/k3s/server/manifests
  sudo sh -c "sed 's/\r\$//' '$src' > /var/lib/rancher/k3s/server/manifests/coredns-custom.yaml"
}

rewrite_game_resolv() {
  [ -n "$NS" ] || return 0
  patch_one() {
    local pod="$1"
    local cid src_resolv
    cid="$(sudo kubectl get pod -n "$NS" "$pod" -o jsonpath='{.status.containerStatuses[0].containerID}' 2>/dev/null | sed 's|containerd://||')"
    [ -n "$cid" ] || return 1
    src_resolv="$(sudo k3s crictl inspect "$cid" 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin)
mounts=(d.get("info") or {}).get("runtimeSpec",{}).get("mounts") or []
for m in mounts:
    if m.get("destination")=="/etc/resolv.conf":
        print(m.get("source",""))
        break
')"
    [ -n "$src_resolv" ] || return 1
    sudo test -f "$src_resolv" || return 1
    if sudo grep -q 'nameserver 8.8.8.8' "$src_resolv" && sudo grep -q 'ndots:1' "$src_resolv"; then
      echo "resolv already patched $pod"
      return 2
    fi
    echo "patch resolv $pod"
    printf '%s' "$RESOLV_BODY" | sudo tee "$src_resolv" >/dev/null
    return 0
  }
  restart_then_repatch() {
    local pod="$1" cid="$2" i new_cid rc
    echo "restart container $pod so Unreal re-reads resolv.conf"
    sudo k3s crictl stop "$cid" >/dev/null 2>&1 || true
    new_cid=""
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
      sleep 2
      new_cid="$(sudo kubectl get pod -n "$NS" "$pod" -o jsonpath='{.status.containerStatuses[0].containerID}' 2>/dev/null | sed 's|containerd://||')"
      if [ -n "$new_cid" ] && [ "$new_cid" != "$cid" ]; then
        break
      fi
    done
    [ -n "$new_cid" ] || return 0
    rc=0
    patch_one "$pod" || rc=$?
    if [ "$rc" -eq 0 ]; then
      echo "restart $pod again after sandbox resolv was rewritten"
      sudo k3s crictl stop "$new_cid" >/dev/null 2>&1 || true
      sleep 4
      patch_one "$pod" || true
    fi
  }
  local pod cid rc
  while read -r pod; do
    [ -n "$pod" ] || continue
    cid="$(sudo kubectl get pod -n "$NS" "$pod" -o jsonpath='{.status.containerStatuses[0].containerID}' 2>/dev/null | sed 's|containerd://||')"
    rc=0
    patch_one "$pod" || rc=$?
    if [ "$rc" -eq 1 ]; then
      echo "skip resolv $pod"
      continue
    fi
    if [ "$rc" -eq 0 ] && [ -n "$cid" ]; then
      restart_then_repatch "$pod" "$cid"
    fi
  done < <(sudo kubectl get pods -n "$NS" --no-headers -o custom-columns=NAME:.metadata.name | grep -E 'sg-survival|sg-overmap' || true)
}

echo "=== dune-fix-fls-dns ==="
apply_coredns
rewrite_game_resolv
echo "=== dune-fix-fls-dns end ==="
