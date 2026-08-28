# Building the Lumen Firecracker rootfs (permanent host)

## Required contracts

1. Kernel: `TBE_FC_KERNEL` points to a bzImage/vmlinux usable by Firecracker.
2. Rootfs ext4: `TBE_FC_ROOTFS` — contains:
   - Python 3.11+
   - systemd **or** busybox init that always starts `lumen-guest.service`
   - `/opt/lumen/supervisor.py` (copy from `lumen/engine/services/sandbox_runtime/guest_agent/supervisor.py`)
   - Mount points `/project` and `/token`
3. Host injects `.lumen_guest/*` into the **project drive** at every start.

## Success gate (host)

`FirecrackerSandboxBackend.start` only returns `running` after serial log contains:

- `lumen-bot-started` (preferred)
- or fails on `lumen-bot-fatal` / timeout (`TBE_FC_BOT_HEALTH_TIMEOUT`, default 90s)

## Suggested build path

```bash
# Example only — operator builds offline on a Linux+KVM host
# 1) debootstrap or alpine rootfs
# 2) install python3, systemd
# 3) copy lumen-guest.service → /etc/systemd/system/
# 4) systemctl enable lumen-guest.service
# 5) pack ext4 → export path for TBE_FC_ROOTFS
```

## Env on host

```
TBE_FC_KERNEL=/var/lib/lumen/vmlinux
TBE_FC_ROOTFS=/var/lib/lumen/rootfs.ext4
TBE_FC_JAILER=/usr/bin/jailer
TBE_FC_REQUIRE_BOT_HEALTH=1
TBE_FC_BOT_HEALTH_TIMEOUT=90
TBE_FC_EGRESS_STRICT=1
TBE_MULTI_TENANT=1
ENVIRONMENT=production
```
