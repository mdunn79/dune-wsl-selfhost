#!/usr/bin/env bash
# Funcom BattleGroup CRD has no dnsPolicy/dnsConfig. hostNetwork Unreal pods
# get ClusterFirstWithHostNet (10.43.0.10 ndots:5) which times out on WSL, so
# Hagga cannot resolve sb-retail.fls.funcom.com (HP3).
# Durable path: dune-fls-dns.service --watch rewrites those sandbox resolv.conf
# files every 5s. One-shot still restarts Unreal only if a rewrite was needed
# (install / map roll). CoreDNS apply stays on the one-shot, not the watcher.
set -euo pipefail
SETUP_SRC="${SETUP_SRC:-}"
RESOLV_BODY=$'nameserver 8.8.8.8\nnameserver 1.1.1.1\noptions ndots:1\n'
BIN=/home/dune/.dune/bin
UNIT=/etc/systemd/system/dune-fls-dns.service
CMD="${1:-}"
NS=""

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
  sed 's/\r$//' "$src" | sudo kubectl apply -f - >/dev/null
  sudo mkdir -p /var/lib/rancher/k3s/server/manifests
  sudo sh -c "sed 's/\r\$//' '$src' > /var/lib/rancher/k3s/server/manifests/coredns-custom.yaml"
}

# Prints patched pod names on stdout (one per line). Quiet if already correct.
patch_game_resolv() {
  local py=(python3)
  if [ "$(id -u)" -ne 0 ]; then
    py=(sudo FLS_DNS_QUIET="${FLS_DNS_QUIET:-0}" python3)
  fi
  "${py[@]}" -c '
import json, os, subprocess, sys
body = """'"$RESOLV_BODY"'"""
quiet = os.environ.get("FLS_DNS_QUIET", "0") == "1"
def run(cmd):
    return subprocess.check_output(cmd, text=True)
d = {"items": []}
for cmd in (["k3s", "crictl", "pods", "-o", "json"], ["sudo", "k3s", "crictl", "pods", "-o", "json"]):
    try:
        d = json.loads(run(cmd))
        break
    except Exception:
        continue
roots = [
    "/var/lib/rancher/k3s/agent/containerd/io.containerd.grpc.v1.cri/sandboxes",
    "/run/k3s/containerd/io.containerd.grpc.v1.cri/sandboxes",
]
for it in d.get("items") or []:
    name = ((it.get("metadata") or {}).get("name") or "")
    if "-sg-" not in name:
        continue
    sid = it.get("id") or ""
    if not sid:
        continue
    path = ""
    for root in roots:
        p = os.path.join(root, sid, "resolv.conf")
        if os.path.isfile(p):
            path = p
            break
    if not path:
        continue
    try:
        cur = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    if "nameserver 8.8.8.8" in cur and "ndots:1" in cur:
        if not quiet:
            print("resolv already patched", name, file=sys.stderr)
        continue
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError as e:
        print("skip resolv %s: %s" % (name, e), file=sys.stderr)
        continue
    print(name)
    print("patch resolv", name, file=sys.stderr)
'
}

restart_game_container() {
  local pod="$1" cid i new_cid
  [ -n "$NS" ] || return 0
  cid="$(sudo kubectl get pod -n "$NS" "$pod" -o jsonpath='{.status.containerStatuses[0].containerID}' 2>/dev/null | sed 's|containerd://||')"
  [ -n "$cid" ] || return 0
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
  FLS_DNS_QUIET=1 patch_game_resolv >/dev/null || true
}

install_unit() {
  install -d -o dune -g dune -m 755 /home/dune/.dune /home/dune/.dune/bin
  if [ -f "$BIN/dune-fls-dns.service" ]; then
    sed 's/\r$//' "$BIN/dune-fls-dns.service" > "$UNIT"
  fi
  systemctl daemon-reload
  systemctl enable dune-fls-dns.service >/dev/null
  if systemctl is-active --quiet dune-fls-dns.service; then
    systemctl restart dune-fls-dns.service
  else
    systemctl start dune-fls-dns.service
  fi
  echo "dune-fls-dns.service enabled (rewrites Unreal sandbox DNS; does not bounce maps)"
}

watch_loop() {
  echo "=== dune-fix-fls-dns watch ==="
  while true; do
    FLS_DNS_QUIET=1 patch_game_resolv || true
    sleep 5
  done
}

if [ "$CMD" = "--install" ]; then
  install_unit
  exit 0
fi

if [ "$CMD" = "--watch" ]; then
  set +e
  watch_loop
  exit 0
fi

echo "=== dune-fix-fls-dns ==="
NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
apply_coredns
patched="$(patch_game_resolv || true)"
if [ -n "$patched" ]; then
  while read -r pod; do
    [ -n "$pod" ] || continue
    restart_game_container "$pod"
  done <<< "$patched"
else
  echo "Unreal sandbox DNS already 8.8.8.8 ndots:1"
fi
echo "=== dune-fix-fls-dns end ==="
