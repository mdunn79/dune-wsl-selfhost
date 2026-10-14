#!/usr/bin/env bash
# Map Funcom k8s service names to pod IPs in /etc/hosts and Unreal sandbox hosts.
# hostNetwork game servers cannot TLS through ClusterIP/kube-proxy.
set -euo pipefail
TAG='# dune-k8s-services'
TMP=/home/dune/.dune/dune-ep.json
NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep '^funcom-seabass-' | head -n1 || true)"
if [ -z "$NS" ]; then
  echo "ERROR: no funcom-seabass-* namespace" >&2
  exit 1
fi

sudo mkdir -p /home/dune/.dune
PREV=/home/dune/.dune/dune-hosts.prev
if [ -f /home/dune/.dune/dune-hosts.txt ]; then
  sudo cp /home/dune/.dune/dune-hosts.txt "$PREV"
else
  sudo rm -f "$PREV"
fi
sudo kubectl get endpoints -n "$NS" -o json > "$TMP"
python3 - "$TMP" "$TAG" <<'PY'
import json,sys
path, tag = sys.argv[1], sys.argv[2]
d=json.load(open(path))
lines=[]
for i in d.get("items",[]):
    name=i["metadata"]["name"]
    ns=i["metadata"]["namespace"]
    ips=[]
    for s in i.get("subsets") or []:
        for a in s.get("addresses") or []:
            ip=a.get("ip")
            if ip:
                ips.append(ip)
    if not ips:
        continue
    aliases=" ".join([name, f"{name}.{ns}", f"{name}.{ns}.svc.cluster.local"])
    lines.append(f"{ips[0]} {aliases} {tag}")
text="\n".join(lines)+"\n"
open("/home/dune/.dune/dune-hosts.txt","w").write(text)
print(text, end="")
PY
sudo sed -i "/${TAG}/d" /etc/hosts
sudo sh -c 'cat /home/dune/.dune/dune-hosts.txt >> /etc/hosts'
BG="${NS#funcom-seabass-}"
getent hosts "${BG}-mq-game-svc" || true
getent hosts "${BG}-mq-admin-svc" || true
getent hosts "${BG}-db-dbdepl-svc" || true

# hostNetwork Unreal/libcurl sometimes fails WSL DNS for Funcom FLS (HP3 identity).
FLS_TAG='# dune-fls'
python3 - "$FLS_TAG" <<'PY' || true
import socket, sys
tag = sys.argv[1]
try:
    ip = socket.getaddrinfo("sb-retail.fls.funcom.com", 443, socket.AF_INET)[0][4][0]
except OSError as e:
    print("skip FLS hosts pin:", e)
    raise SystemExit(0)
open("/home/dune/.dune/dune-fls-hosts.txt", "w").write(f"{ip} sb-retail.fls.funcom.com {tag}\n")
print(f"{ip} sb-retail.fls.funcom.com")
PY
if [ -f /home/dune/.dune/dune-fls-hosts.txt ]; then
  sudo sed -i "/${FLS_TAG}/d" /etc/hosts
  sudo sh -c 'cat /home/dune/.dune/dune-fls-hosts.txt >> /etc/hosts'
fi

# hostNetwork Unreal uses the containerd sandbox hosts file, not WSL /etc/hosts.
sudo python3 - "$TAG" <<'PY' || true
import json, os, subprocess, sys
tag = sys.argv[1]
body_path = "/home/dune/.dune/dune-hosts.txt"
if not os.path.isfile(body_path):
    raise SystemExit(0)
body = open(body_path, encoding="utf-8").read()
if tag not in body:
    raise SystemExit(0)
d = {"items": []}
for cmd in (["k3s", "crictl", "pods", "-o", "json"], ["sudo", "k3s", "crictl", "pods", "-o", "json"]):
    try:
        d = json.loads(subprocess.check_output(cmd, text=True, timeout=30))
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
    path = ""
    for root in roots:
        p = os.path.join(root, sid, "hosts")
        if os.path.isfile(p):
            path = p
            break
    if not path:
        continue
    try:
        cur = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    keep = [ln for ln in cur.splitlines() if tag not in ln]
    while keep and keep[-1].strip() == "":
        keep.pop()
    new = "\n".join(keep) + "\n" + body
    if not body.endswith("\n"):
        new += "\n"
    if new == cur:
        continue
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    except OSError as e:
        print("skip sandbox hosts %s: %s" % (name, e), file=sys.stderr)
        continue
    print("sandbox hosts", name)
PY

# MQ pod IPs changed: Unreal does not re-read hosts. Restart only sg- containers
# whose current log already shows admin RMQ TCP failure. Flag lasts 360s so a
# scrape that happens before the first socket error can still recover.
sudo python3 - "$NS" "$PREV" /home/dune/.dune/dune-hosts.txt <<'PY' || true
import json, os, subprocess, sys, time
ns, prev_path, new_path = sys.argv[1], sys.argv[2], sys.argv[3]
FLAG = "/home/dune/.dune/mq-ip-changed"
WINDOW = 360

def mq_pair(path):
    admin = game = ""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return "", ""
    for line in text.splitlines():
        if not line.strip():
            continue
        ip = line.split()[0]
        if "mq-admin-svc" in line:
            admin = ip
        if "mq-game-svc" in line:
            game = ip
    return admin, game

def run(cmd, timeout=30):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout or ""

prev, new = mq_pair(prev_path), mq_pair(new_path)
now = time.time()
if prev[0] and new[0] and prev != new:
    try:
        open(FLAG, "w", encoding="utf-8").write("%.0f\n" % now)
    except OSError:
        pass
if not os.path.isfile(FLAG):
    raise SystemExit(0)
try:
    age = now - float(open(FLAG, encoding="utf-8").read().strip() or "0")
except (OSError, ValueError):
    age = WINDOW + 1
if age > WINDOW:
    try:
        os.remove(FLAG)
    except OSError:
        pass
    raise SystemExit(0)
code, out = run(["sudo", "kubectl", "get", "pods", "-n", ns, "-o", "json"], timeout=40)
if code != 0:
    raise SystemExit(0)
try:
    items = json.loads(out).get("items") or []
except Exception:
    raise SystemExit(0)
for it in items:
    name = ((it.get("metadata") or {}).get("name") or "")
    if "-sg-" not in name:
        continue
    phase = ((it.get("status") or {}).get("phase") or "")
    if phase in ("Succeeded", "Failed"):
        continue
    code, logs = run(["sudo", "kubectl", "logs", "-n", ns, name, "--tail=80"], timeout=30)
    if code != 0 or "Failed to open TCP socket" not in logs or "mq-admin-svc" not in logs:
        continue
    cid = ""
    for cs in (it.get("status") or {}).get("containerStatuses") or []:
        cid = (cs.get("containerID") or "").replace("containerd://", "")
        if cid:
            break
    if not cid:
        continue
    print("rmq recover", name, file=sys.stderr)
    run(["sudo", "k3s", "crictl", "stop", cid], timeout=60)
PY
