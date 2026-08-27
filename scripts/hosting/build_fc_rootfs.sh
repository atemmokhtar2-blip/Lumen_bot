#!/usr/bin/env bash
# Build a minimal ext4 rootfs suitable for Lumen Telegram bots inside Firecracker.
# Produces: rootfs.ext4 (+ optional vmlinux copy instructions)
#
# Requires root (debootstrap + loop mount) on Debian/Ubuntu host.
# This is an operator script — not invoked at bot-start time.
set -euo pipefail

ROOTFS_SIZE_MB="${FC_ROOTFS_SIZE_MB:-2048}"
OUT_DIR="${FC_OUT_DIR:-/var/lib/lumen/firecracker}"
SUITE="${FC_DEBIAN_SUITE:-bookworm}"
MIRROR="${FC_DEBIAN_MIRROR:-http://deb.debian.org/debian}"

mkdir -p "${OUT_DIR}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

IMG="${OUT_DIR}/rootfs.ext4"
MNT="${WORK}/mnt"
mkdir -p "${MNT}"

echo "Creating sparse image ${IMG} (${ROOTFS_SIZE_MB}M)"
rm -f "${IMG}"
truncate -s "${ROOTFS_SIZE_MB}M" "${IMG}"
mkfs.ext4 -F -q "${IMG}"
mount -o loop "${IMG}" "${MNT}"

cleanup() {
  umount "${MNT}" 2>/dev/null || true
}
trap cleanup EXIT

echo "debootstrap ${SUITE}"
debootstrap --variant=minbase "${SUITE}" "${MNT}" "${MIRROR}"

# Essential packages for generated Telegram bots
chroot "${MNT}" apt-get update -qq
chroot "${MNT}" apt-get install -y -qq --no-install-recommends \
  python3 python3-pip python3-venv ca-certificates curl \
  iproute2 procps tini

# Guest init: mount project + token drives if present, export env, run bot
cat > "${MNT}/sbin/lumen-bot-init" << 'EOF'
#!/bin/sh
set -e
mkdir -p /project /run/token /app
echo "lumen-guest-ready" >&2
# Firecracker extra drives: /dev/vdb=project, /dev/vdc=token
if [ -b /dev/vdb ]; then
  mount -o ro /dev/vdb /project || true
fi
if [ -b /dev/vdc ]; then
  mount -o ro /dev/vdc /run/token || true
fi
if [ -f /run/token/BOT_TOKEN ]; then
  export BOT_TOKEN="$(cat /run/token/BOT_TOKEN)"
  export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
fi
if [ -f /run/token/env.json ]; then
  if command -v python3 >/dev/null 2>&1; then
    eval "$(python3 -c "import json,shlex; d=json.load(open('/run/token/env.json'));
print(' '.join(f'export {k}={shlex.quote(str(v))}' for k,v in d.items()))" 2>/dev/null || true)"
  fi
fi
# MMDS fallback (Firecracker metadata service)
if [ -z "${BOT_TOKEN:-}" ] && command -v curl >/dev/null 2>&1; then
  UD="$(curl -fsS --max-time 2 http://169.254.169.254/latest/user-data/ 2>/dev/null || true)"
  if [ -n "$UD" ] && command -v python3 >/dev/null 2>&1; then
    export BOT_TOKEN="$(python3 -c "import json,sys; d=json.loads(sys.argv[1]) if sys.argv[1].startswith('{') else {}; print(d.get('BOT_TOKEN',''))" "$UD" 2>/dev/null || true)"
    export TELEGRAM_BOT_TOKEN="${BOT_TOKEN}"
  fi
fi
cd /project 2>/dev/null || cd /
echo "lumen-bot-started" >&2
if [ -f /project/main.py ]; then
  exec python3 /project/main.py
elif [ -f /project/bot.py ]; then
  exec python3 /project/bot.py
elif [ -f /project/app.py ]; then
  exec python3 /project/app.py
else
  echo "lumen-bot-init: no entrypoint found under /project" >&2
  sleep 3600
fi
EOF
chmod 0755 "${MNT}/sbin/lumen-bot-init"

# Use tini as PID1 then lumen-bot-init
if [ -x "${MNT}/usr/bin/tini" ]; then
  ln -sf /usr/bin/tini "${MNT}/sbin/init"
  # tini will need a default — provide inittab-less: replace with wrapper
  cat > "${MNT}/sbin/init" << 'EOF'
#!/bin/sh
exec /usr/bin/tini -g -- /sbin/lumen-bot-init
EOF
  chmod 0755 "${MNT}/sbin/init"
else
  ln -sf /sbin/lumen-bot-init "${MNT}/sbin/init"
fi

# Minimal fstab
cat > "${MNT}/etc/fstab" << 'EOF'
/dev/vda / ext4 defaults 0 1
EOF

chroot "${MNT}" apt-get clean
rm -rf "${MNT}/var/lib/apt/lists"/*

umount "${MNT}"
trap - EXIT

echo "Rootfs ready: ${IMG}"
echo "Kernel: obtain a Firecracker-compatible vmlinux (e.g. from firecracker CI artifacts)"
echo "  export TBE_FC_ROOTFS=${IMG}"
echo "  export TBE_FC_KERNEL=/path/to/vmlinux"
