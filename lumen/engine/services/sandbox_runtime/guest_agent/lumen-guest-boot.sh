#!/bin/sh
# Minimal guest init fragment for Lumen permanent hosting rootfs.
# Bake into rootfs as /usr/local/bin/lumen-guest-boot or systemd unit ExecStart.
set -eu
PROJECT="${LUMEN_PROJECT_ROOT:-/project}"
TOKEN_DIR="${LUMEN_TOKEN_DIR:-/token}"
mkdir -p /run/lumen 2>/dev/null || true

# Mount virtio project/token if not already mounted (device names depend on rootfs)
# Operators should ensure /project and /token are mounted before this runs.

export LUMEN_PROJECT_ROOT="$PROJECT"
export LUMEN_TOKEN_DIR="$TOKEN_DIR"

if [ -f "$PROJECT/.lumen_guest/supervisor.py" ]; then
  exec python3 "$PROJECT/.lumen_guest/supervisor.py"
fi
if [ -f /opt/lumen/supervisor.py ]; then
  exec python3 /opt/lumen/supervisor.py
fi
echo "lumen-bot-fatal supervisor_missing" >&2
exit 1
