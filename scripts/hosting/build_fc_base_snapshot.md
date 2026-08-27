# Building a Firecracker base snapshot (warm pool)

Competitive hosts pre-build a **guest-ready** Full snapshot once, then resume
per-tenant VMs from it (`TBE_FC_WARM_POOL=1`).

## Prerequisites
- `/dev/kvm`, `firecracker`, `jailer` (optional for lab), `iproute2`
- `TBE_FC_KERNEL`, `TBE_FC_ROOTFS` built via `build_fc_rootfs.sh`
- CAP_NET_ADMIN for TAP

## Lab procedure (operator)

1. Cold-boot one microVM with empty project until serial shows `lumen-guest-ready`.
2. Pause + snapshot via API (or Python):

```python
from pathlib import Path
from lumen.engine.services.sandbox_runtime.fc_snapshot import (
    artifacts_for, create_full_snapshot,
)
arts = artifacts_for("base")
create_full_snapshot(Path("/path/to/firecracker.sock"), arts)
```

3. Enable:

```
export TBE_FC_WARM_POOL=1
export TBE_FC_SNAPSHOT_DIR=/var/lib/lumen/fc_snapshots
export TBE_FC_SNAPSHOT_LABEL=base
```

4. Subsequent starts call `try_warm_start` before cold configure.

**Note:** Block devices (project/token) are not inside the snapshot; attach
fresh drives after resume in a full production orchestrator iteration.
