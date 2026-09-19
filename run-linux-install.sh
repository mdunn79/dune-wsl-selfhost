#!/usr/bin/env bash
# Tiny Windows->Linux handoff. Arg 1 is the /mnt/c/... path to this installer folder.
set -euo pipefail
SRC="${1:?installer folder path}"
set -a
# shellcheck disable=SC1091
sed 's/\r$//' "$SRC/install.env" > /tmp/dune-install.env
. /tmp/dune-install.env
set +a
# Token goes to /tmp until user 'dune' exists (useradd -m fails if /home/dune was created early).
if [ -f "$SRC/.fls-token" ]; then
  cp "$SRC/.fls-token" /tmp/dune-fls.token
  chmod 600 /tmp/dune-fls.token
fi
sed 's/\r$//' "$SRC/install-dune-inside-wsl.sh" > /tmp/install-dune-inside-wsl.sh
exec bash /tmp/install-dune-inside-wsl.sh
