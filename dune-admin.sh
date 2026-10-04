#!/usr/bin/env bash
# Start or install the LAN web admin (TCP 18889 on LanIp).
set -euo pipefail
export HOME=/home/dune
export PYTHONUNBUFFERED=1
BIN=/home/dune/.dune/bin
UNIT=/etc/systemd/system/dune-admin.service

if [ "${1:-}" = "--install" ]; then
  install -d -o dune -g dune -m 755 /home/dune/.dune /home/dune/.dune/bin
  if [ ! -s /home/dune/.dune/admin.token ]; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > /home/dune/.dune/admin.token
    chown dune:dune /home/dune/.dune/admin.token
    chmod 600 /home/dune/.dune/admin.token
  fi
  if [ -f "$BIN/dune-admin.service" ]; then
    sed 's/\r$//' "$BIN/dune-admin.service" > "$UNIT"
  fi
  systemctl daemon-reload
  systemctl enable dune-admin.service
  if systemctl is-active --quiet dune-admin.service; then
    systemctl restart dune-admin.service
  else
    systemctl start dune-admin.service
  fi
  echo "dune-admin enabled. Open http://$(tr -d '[:space:]' < /home/dune/.dune/lan-ip.conf):18889"
  echo "Token is /home/dune/.dune/admin.token (not printed)."
  exit 0
fi

exec python3 "$BIN/dune-admin.py"
