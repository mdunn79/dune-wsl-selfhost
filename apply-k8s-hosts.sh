#!/usr/bin/env bash
# Map Funcom k8s service names to pod IPs in /etc/hosts.
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
