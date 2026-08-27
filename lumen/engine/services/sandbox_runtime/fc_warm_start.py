"""Warm-start Firecracker from Full snapshot (competitive cold-start path).

Requires operator-built base snapshot under TBE_FC_SNAPSHOT_DIR/<label>/.
When TBE_FC_WARM_POOL=1 and snapshot exists, start path can resume instead of
cold boot (kernel+rootfs reconfigure).
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from .fc_snapshot import SnapshotArtifacts, get_warm_pool, load_and_resume

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def warm_pool_enabled() -> bool:
    return _flag("TBE_FC_WARM_POOL", "0")


def try_warm_start(
    *,
    firecracker_bin: str,
    sock: Path,
    log_path: Path,
    label: str = "base",
) -> Optional[int]:
    """Start VMM and load snapshot. Returns pid or None if warm path unavailable."""
    if not warm_pool_enabled():
        return None
    pool = get_warm_pool()
    arts = pool.get(label) or pool.get(os.environ.get("TBE_FC_SNAPSHOT_LABEL") or "base")
    if arts is None:
        logger.info("warm_pool: no snapshot for label=%s", label)
        return None
    log_f = open(log_path, "a")
    try:
        if sock.exists() or sock.is_symlink():
            try:
                sock.unlink()
            except OSError:
                pass
        proc = subprocess.Popen(
            [firecracker_bin, "--api-sock", str(sock)],
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        log_f.close()
        raise
    # wait sock
    for _ in range(100):
        if sock.exists():
            break
        if proc.poll() is not None:
            raise RuntimeError("warm_start_vmm_exited_early")
        time.sleep(0.05)
    else:
        try:
            proc.kill()
        except OSError:
            pass
        raise RuntimeError("warm_start_sock_timeout")
    try:
        load_and_resume(sock, arts)
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        raise
    logger.info("warm_start resumed label=%s pid=%s", arts.label, proc.pid)
    return int(proc.pid)
