#!/usr/bin/env bash
# Copy Lumen guest agent into an already-mounted rootfs tree.
# Usage: ./install_guest_into_rootfs.sh /mnt/rootfs
set -euo pipefail
ROOT="${1:?rootfs mount path}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT="$REPO_ROOT/lumen/engine/services/sandbox_runtime/guest_agent"
mkdir -p "$ROOT/opt/lumen" "$ROOT/project" "$ROOT/token" "$ROOT/etc/systemd/system"
cp -f "$AGENT/supervisor.py" "$ROOT/opt/lumen/supervisor.py"
cp -f "$AGENT/lumen-guest-boot.sh" "$ROOT/opt/lumen/lumen-guest-boot.sh"
chmod 755 "$ROOT/opt/lumen/lumen-guest-boot.sh"
cp -f "$(dirname "$0")/lumen-guest.service" "$ROOT/etc/systemd/system/lumen-guest.service"
if [[ -d "$ROOT/etc/systemd/system/multi-user.target.wants" ]]; then
  ln -sf /etc/systemd/system/lumen-guest.service     "$ROOT/etc/systemd/system/multi-user.target.wants/lumen-guest.service"
fi
echo "Installed guest agent into $ROOT"
