#!/usr/bin/env bash
# Install official Google gVisor (runsc) and register it as a Docker runtime.
# Sources (official only):
#   https://gvisor.dev/docs/user_guide/install/
#   https://gvisor.dev/docs/user_guide/quick_start/docker/
#
# This script does NOT invent a sandbox. It installs the real runsc binary
# published by Google and registers it with Docker via `runsc install`.
set -euo pipefail

log()  { printf '[gvisor-install] %s\n' "$*"; }
die()  { printf '[gvisor-install] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

if [[ "${EUID}" -ne 0 ]]; then
  die "run as root (sudo). Example: sudo bash scripts/hosting/install_gvisor.sh"
fi

need uname
need curl
need tar
need sha512sum

ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=aarch64 ;;
  *) die "unsupported architecture: ${ARCH} (gVisor supports x86_64 and aarch64)" ;;
esac

# Prefer Debian/Ubuntu package when apt is available (official Google apt repo).
install_via_apt() {
  need apt-get
  need gpg
  log "installing runsc via official Google apt repository"
  # Key + repo from gvisor.dev install guide
  curl -fsSL https://gvisor.dev/archive.key \
    | gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
    > /etc/apt/sources.list.d/gvisor.list
  apt-get update -qq
  apt-get install -y runsc
  log "apt package runsc installed"
}

# Fallback: official release tarball from Google Cloud Storage.
install_via_release_tarball() {
  local url="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp}"' RETURN

  log "downloading official release from ${url}"
  curl -fsSL -o "${tmp}/gvisor.tar.bz2"       "${url}/gvisor.tar.bz2"
  curl -fsSL -o "${tmp}/gvisor.tar.bz2.sha512" "${url}/gvisor.tar.bz2.sha512"

  (
    cd "${tmp}"
    sha512sum -c gvisor.tar.bz2.sha512
  ) || die "sha512 verification failed — refusing to install"

  tar -xjf "${tmp}/gvisor.tar.bz2" -C /usr/local/bin
  chmod +x /usr/local/bin/runsc
  # containerd shim + gvisor-bin/ sidecar binaries ship in the same tarball
  if [[ -f /usr/local/bin/containerd-shim-runsc-v1 ]]; then
    chmod +x /usr/local/bin/containerd-shim-runsc-v1
  fi
  log "installed runsc to /usr/local/bin/runsc"
}

# Register runsc with Docker (official: `runsc install`).
register_docker_runtime() {
  if ! command -v docker >/dev/null 2>&1; then
    log "docker not found — skipped runtime registration (install Docker then re-run)"
    return 0
  fi
  if ! command -v runsc >/dev/null 2>&1; then
    die "runsc binary not on PATH after install"
  fi

  log "registering runsc as Docker runtime (official: runsc install)"
  runsc install
  # Prefer reload; fall back to restart if needed
  if command -v systemctl >/dev/null 2>&1; then
    systemctl reload docker 2>/dev/null || systemctl restart docker
  elif command -v service >/dev/null 2>&1; then
    service docker reload 2>/dev/null || service docker restart
  else
    log "WARNING: could not reload docker daemon automatically — restart docker manually"
  fi
}

verify() {
  command -v runsc >/dev/null 2>&1 || die "runsc not on PATH"
  log "runsc version: $(runsc --version 2>/dev/null | head -1 || runsc -version 2>/dev/null | head -1 || echo unknown)"

  if command -v docker >/dev/null 2>&1; then
    local runtimes
    runtimes="$(docker info --format '{{json .Runtimes}}' 2>/dev/null || true)"
    if echo "${runtimes}" | grep -qi runsc; then
      log "Docker reports runsc runtime: OK"
    else
      log "WARNING: Docker does not list runsc yet — restart docker and re-check: docker info | grep -i runsc"
    fi
  fi
}

main() {
  log "official Google gVisor install (runsc)"
  if command -v apt-get >/dev/null 2>&1 && command -v gpg >/dev/null 2>&1; then
    if install_via_apt; then
      :
    else
      log "apt path failed — falling back to official release tarball"
      install_via_release_tarball
    fi
  else
    install_via_release_tarball
  fi
  register_docker_runtime
  verify
  log "done. Use: docker run --rm --runtime=runsc hello-world"
  log "Lumen: set TBE_SANDBOX_BACKEND=gvisor  (or auto with TBE_PREFER_GVISOR=1)"
}

main "$@"
