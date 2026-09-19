#!/usr/bin/env bash
# Linux half of Install-DuneBattlegroup.ps1. Run as root, then drops to user dune.
# Does not print the Funcom token.
set -euo pipefail

SETUP_SRC="${SETUP_SRC:?set SETUP_SRC to this installer folder via /mnt/c/...}"
WORLD_NAME="${DUNE_WORLD_NAME:?set DUNE_WORLD_NAME}"
REGION_INDEX="${DUNE_REGION_INDEX:-3}"
LAN_IP="${DUNE_LAN_IP:?set DUNE_LAN_IP}"
PLAY_STYLE="${DUNE_PLAY_STYLE:-CasualPve}"
DOWNLOAD_PATH=/home/dune/.dune/download
SCRIPTS="$DOWNLOAD_PATH/scripts"
TOKEN_FILE=/home/dune/.dune/.fls-token

lf() {
  # Copy a Windows-side script into Linux with LF endings.
  local src="$1" dest="$2"
  sed 's/\r$//' "$src" > "$dest"
  chmod +x "$dest"
}

as_dune() {
  sudo -u dune -H bash -lc "$*"
}

echo "=== dune linux install ==="
echo "world=$WORLD_NAME region=$REGION_INDEX ip=$LAN_IP playstyle=$PLAY_STYLE"

if ! grep -q avx2 /proc/cpuinfo; then
  echo "ERROR: CPU lacks AVX2 (Funcom Unreal requirement)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl tar gzip python3 openssl iptables iproute2 sudo

if ! id dune >/dev/null 2>&1; then
  useradd -m -s /bin/bash dune
fi
echo 'dune ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dune
chmod 440 /etc/sudoers.d/dune
# systemd belongs in /etc/wsl.conf on the Windows/PS1 side; changing it here cannot take effect mid-run.

install -d -o dune -g dune -m 755 /home/dune/.dune /home/dune/.dune/bin /home/dune/.local/bin /home/dune/Steam
if [ -f /tmp/dune-fls.token ] && [ ! -s "$TOKEN_FILE" ]; then
  install -m 600 -o dune -g dune /tmp/dune-fls.token "$TOKEN_FILE"
  rm -f /tmp/dune-fls.token
fi

if [ ! -x /home/dune/Steam/steamcmd.sh ]; then
  echo "=== install SteamCMD for dune ==="
  curl -fsSL https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz \
    | sudo -u dune tar -xz -C /home/dune/Steam
fi
ln -sfn /home/dune/Steam/steamcmd.sh /home/dune/.local/bin/steamcmd
chown -h dune:dune /home/dune/.local/bin/steamcmd || true

if [ -f "$SCRIPTS/setup.sh" ] && [ -d "$DOWNLOAD_PATH/images/operators/crds" ]; then
  echo "=== SteamCMD depot already present; skipping app_update ==="
else
  echo "=== SteamCMD Linux depot 4754530 ==="
  as_dune "export HOME=/home/dune PATH=/home/dune/.local/bin:\$PATH
    /home/dune/Steam/steamcmd.sh +@ShutdownOnFailedCommand 1 +@NoPromptForPassword 1 \
      +force_install_dir $DOWNLOAD_PATH +login anonymous +app_update 4754530 +quit"
fi
if [ ! -f "$SCRIPTS/setup.sh" ] || [ ! -d "$DOWNLOAD_PATH/images/operators/crds" ]; then
  echo "ERROR: depot missing scripts/setup.sh or operator CRDs under $DOWNLOAD_PATH" >&2
  ls -la "$DOWNLOAD_PATH" || true
  exit 1
fi
chown -R dune:dune /home/dune/.dune /home/dune/Steam /home/dune/.local

echo "=== install helper scripts ==="
lf "$SETUP_SRC/patch-vendor.py" /tmp/patch-vendor.py
lf "$SETUP_SRC/dune-bootstrap-kubernetes.sh" /home/dune/dune-bootstrap-kubernetes.sh
lf "$SETUP_SRC/apply-k8s-hosts.sh" /home/dune/.dune/bin/apply-k8s-hosts.sh
lf "$SETUP_SRC/dune-ensure-join.sh" /home/dune/.dune/bin/dune-ensure-join.sh
lf "$SETUP_SRC/dune-maintain.sh" /home/dune/.dune/bin/dune-maintain.sh
chown dune:dune /home/dune/dune-bootstrap-kubernetes.sh /home/dune/.dune/bin/*

echo "=== patch Funcom Alpine/OpenRC scripts for systemd ==="
(
  cd "$SCRIPTS"
  python3 /tmp/patch-vendor.py
  chmod +x setup.sh setup/k3s.sh setup/helper.sh setup/experimental_swap.sh battlegroup.sh
)

echo "=== k3s ==="
sudo mkdir -p /etc/rancher/k3s/config.yaml.d
sed 's/\r$//' "$SETUP_SRC/99-dune.yaml" | sudo tee /etc/rancher/k3s/config.yaml >/dev/null
if ! command -v k3s >/dev/null 2>&1; then
  as_dune "bash $SCRIPTS/setup/k3s.sh"
else
  echo "k3s already installed"
  systemctl enable k3s >/dev/null 2>&1 || true
  systemctl start k3s
fi

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
k3s_ok=0
for i in $(seq 1 60); do
  if [ -S /run/k3s/containerd/containerd.sock ] && kubectl get --raw=/readyz >/dev/null 2>&1; then
    echo "k3s ready"
    k3s_ok=1
    break
  fi
  sleep 5
done
if [ "$k3s_ok" -ne 1 ]; then
  echo "ERROR: k3s did not become ready" >&2
  systemctl status k3s --no-pager || true
  exit 1
fi

echo "=== load images and Funcom operators ==="
as_dune "/home/dune/dune-bootstrap-kubernetes.sh"

echo "=== battlegroup CLI ==="
as_dune "bash $SCRIPTS/setup/system.sh"
ln -sfn "$SCRIPTS/battlegroup.sh" /home/dune/.dune/bin/battlegroup
ln -sfn "$SCRIPTS/bg-util" /home/dune/.dune/bin/bg-util
chmod +x "$SCRIPTS/battlegroup.sh" "$SCRIPTS/bg-util"
chown -h dune:dune /home/dune/.dune/bin/battlegroup /home/dune/.dune/bin/bg-util || true

if sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep -q '^funcom-seabass-'; then
  echo "World namespace already exists; skipping world.sh"
else
  if [ ! -s "$TOKEN_FILE" ]; then
    echo "ERROR: Funcom token missing at $TOKEN_FILE" >&2
    exit 1
  fi
  sed -i 's/\r$//' "$TOKEN_FILE"
  TOKEN="$(tr -d '\n\r' < "$TOKEN_FILE")"
  python3 - <<'PY'
from pathlib import Path
world = Path("/home/dune/.dune/download/scripts/setup/world.sh")
text = world.read_text()
text = text.replace(
    'sed -i "s/{FLS_SECRET}/$G_FLS_SECRET/g"',
    'sed -i "s|{FLS_SECRET}|$G_FLS_SECRET|g"',
)
world.write_text(text)
tpl = Path("/home/dune/.dune/download/scripts/setup/templates/world-template.yaml")
t = tpl.read_text()
t = t.replace("title: {WORLD_NAME}", 'title: "{WORLD_NAME}"')
tpl.write_text(t)
print("patched world.sh and world-template.yaml")
PY
  mkdir -p /home/dune/.dune/bin
  printf 'manual\n' > /home/dune/.dune/battlegroup-ip.conf
  printf '\n\n\n%s\n' "$LAN_IP" > /home/dune/.dune/settings.conf
  CFG_DST="$SCRIPTS/setup/config"
  if [ "$PLAY_STYLE" = "Official" ]; then
    echo "PlayStyle=Official; leaving Funcom default UserSettings"
  else
    echo "PlayStyle=CasualPve; applying NoPVP + casual progression inis"
    for f in UserEngine.ini UserGame.ini UserServerCustomSettings.ini; do
      sed 's/\r$//' "$SETUP_SRC/$f" > "$CFG_DST/$f"
    done
    python3 - "$CFG_DST/UserEngine.ini" "$WORLD_NAME" <<'PY'
from pathlib import Path
import sys
path, name = Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
# Keep the display name in lockstep with the Funcom world title.
import re
text = re.sub(
    r'^Bgd\.ServerDisplayName=.*$',
    'Bgd.ServerDisplayName="%s"' % name.replace('"', ""),
    text,
    flags=re.M,
)
path.write_text(text)
PY
  fi
  chown -R dune:dune /home/dune/.dune
  echo "=== world.sh ==="
  # Do not use bash -lc here: world.sh must inherit the piped answers on stdin.
  printf '%s\n' "$WORLD_NAME" "$REGION_INDEX" "$TOKEN" | sudo -u dune -H bash "$SCRIPTS/setup/world.sh"
fi

echo "=== HOST_DATACENTER_IP_ADDRESS=$LAN_IP ==="
python3 - <<PY
from pathlib import Path
ip = "$LAN_IP"
for path in Path("/home/dune/.dune").glob("sh-*.yaml"):
    if path.name.endswith("-fls-secret.yaml") or path.name.endswith("-rmq-secret.yaml"):
        continue
    text = path.read_text()
    updated = text.replace("value: 127.0.0.1", f"value: {ip}")
    if updated != text:
        path.write_text(updated)
        print(f"patched {path}")
PY

NS="$(sudo kubectl get ns --no-headers -o custom-columns=NAME:.metadata.name | grep '^funcom-seabass-' | head -n1 || true)"
if [ -z "$NS" ]; then
  echo "ERROR: world namespace was not created" >&2
  sudo kubectl get ns
  exit 1
fi
BG="${NS#funcom-seabass-}"
echo "Namespace=$NS BattleGroup=$BG"

PATCH="$(
  sudo kubectl get battlegroup "$BG" -n "$NS" -o json \
    | DUNE_LAN_IP="$LAN_IP" python3 -c 'import json,os,sys
bg=json.load(sys.stdin)
player_ip=os.environ["DUNE_LAN_IP"]
ops=[]
def esc(part):
    return str(part).replace("~","~0").replace("/","~1")
def walk(node,path):
    if isinstance(node,dict):
        envs=node.get("envVars")
        if isinstance(envs,list):
            for i,item in enumerate(envs):
                if isinstance(item,dict) and item.get("name")=="HOST_DATACENTER_IP_ADDRESS":
                    ops.append({"op":"replace" if "value" in item else "add","path":"/"+"/".join(esc(p) for p in path+["envVars",i,"value"]),"value":player_ip})
        for key,value in node.items():
            walk(value,path+[key])
    elif isinstance(node,list):
        for i,value in enumerate(node):
            walk(value,path+[i])
walk(bg.get("spec",{}),["spec"])
print(json.dumps(ops))'
)"
if [ "$PATCH" != "[]" ]; then
  sudo kubectl patch battlegroup "$BG" -n "$NS" --type=json -p "$PATCH"
  echo "patched live BattleGroup IP"
fi

echo "=== apply images and usersettings ==="
as_dune "$SCRIPTS/battlegroup.sh update-from-downloads" || true
as_dune "$SCRIPTS/battlegroup.sh start" || true
for i in $(seq 1 60); do
  if sudo kubectl get pods -n "$NS" -l role=igw-filebrowser --no-headers 2>/dev/null | grep -q .; then
    break
  fi
  echo "waiting for filebrowser ($i/60)"
  sleep 5
done
as_dune "$SCRIPTS/battlegroup.sh apply-default-usersettings" || true

echo "=== wait maps Ready ==="
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-1200}"
elapsed=0
maps_ok=0
while [ "$elapsed" -lt "$READY_TIMEOUT_SEC" ]; do
  st="$(as_dune /home/dune/.dune/bin/battlegroup status || true)"
  echo "$st"
  if echo "$st" | grep -qE 'Overmap[[:space:]]+Running[[:space:]]+true' \
    && echo "$st" | grep -qE 'Survival_1[[:space:]]+Running[[:space:]]+true'; then
    echo "Maps Ready"
    maps_ok=1
    break
  fi
  sleep 15
  elapsed=$((elapsed + 15))
done
if [ "$maps_ok" -ne 1 ]; then
  echo "ERROR: maps did not become Ready within ${READY_TIMEOUT_SEC}s (join will spin)" >&2
  exit 1
fi

echo "=== bind join ports ==="
as_dune "DUNE_LAN_IP=$LAN_IP /home/dune/.dune/bin/dune-ensure-join.sh"

rm -f "$TOKEN_FILE"
echo "INSTALL_DONE NS=$NS BG=$BG IP=$LAN_IP"
as_dune /home/dune/.dune/bin/battlegroup status || true
