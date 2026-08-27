#!/usr/bin/env bash
# Install Firecracker + Jailer (same version) for Lumen production hosts.
# Requires: Linux x86_64 or aarch64, root for /usr/local/bin, KVM on the host.
set -euo pipefail

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) FC_ARCH="x86_64" ;;
  aarch64|arm64) FC_ARCH="aarch64" ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac

VERSION="${FIRECRACKER_VERSION:-v1.11.0}"
DEST="${FIRECRACKER_INSTALL_DIR:-/usr/local/bin}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Installing Firecracker ${VERSION} (${FC_ARCH}) into ${DEST}"

# Official GitHub release assets: firecracker / jailer binaries
BASE="https://github.com/firecracker-microvm/firecracker/releases/download/${VERSION}"
# Prefer the release tarball when available
TAR="firecracker-${VERSION}-${FC_ARCH}.tgz"
if curl -fsSL -o "${TMP}/${TAR}" "${BASE}/${TAR}"; then
  tar -xzf "${TMP}/${TAR}" -C "${TMP}"
  # Layout varies slightly by version; find binaries
  FC_BIN="$(find "${TMP}" -type f -name firecracker | head -1)"
  JAILER_BIN="$(find "${TMP}" -type f -name jailer | head -1)"
else
  echo "tarball missing; trying direct binary names"
  curl -fsSL -o "${TMP}/firecracker" "${BASE}/firecracker-${VERSION}-${FC_ARCH}"
  curl -fsSL -o "${TMP}/jailer" "${BASE}/jailer-${VERSION}-${FC_ARCH}"
  FC_BIN="${TMP}/firecracker"
  JAILER_BIN="${TMP}/jailer"
fi

if [[ -z "${FC_BIN}" || -z "${JAILER_BIN}" ]]; then
  echo "failed to locate firecracker/jailer in release assets"
  exit 1
fi

install -m 0755 "${FC_BIN}" "${DEST}/firecracker"
install -m 0755 "${JAILER_BIN}" "${DEST}/jailer"

# Production chroot base (must not be world-writable)
mkdir -p /srv/jailer
chmod 0750 /srv/jailer

# KVM access check
if [[ ! -e /dev/kvm ]]; then
  echo "WARNING: /dev/kvm missing — Firecracker cannot run on this host"
else
  echo "KVM: ok"
fi

echo "Installed:"
"${DEST}/firecracker" --version || true
ls -la "${DEST}/firecracker" "${DEST}/jailer"
echo "Next: build guest kernel + rootfs (scripts/hosting/build_fc_rootfs.sh)"
echo "Set: TBE_FIRECRACKER_BIN=${DEST}/firecracker TBE_JAILER_BIN=${DEST}/jailer"
echo "     TBE_FC_KERNEL=... TBE_FC_ROOTFS=... TBE_FC_CHROOT_BASE=/srv/jailer"
