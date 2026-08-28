"""Warm-start Firecracker from Full snapshot (competitive cold-start path).

Requires operator-built base snapshot under TBE_FC_SNAPSHOT_DIR/<label>/.
When TBE_FC_WARM_POOL=1 and snapshot exists, start path can resume instead of
cold boot (kernel+rootfs reconfigure).

Supports:
  - direct (no jailer) — lab / TBE_FC_ALLOW_NO_JAILER
  - jailed — production: jailer + load snapshot on API socket inside chroot
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from .fc_snapshot import SnapshotArtifacts, fast_link_or_copy, get_warm_pool, load_and_resume

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
    """Start VMM (no jailer) and load snapshot. Returns pid or None if unavailable."""
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
        metrics = load_and_resume(sock, arts) or {}
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        raise
    logger.info(
        "warm_start resumed label=%s pid=%s load_ms=%s",
        arts.label, proc.pid, metrics.get("load_ms"),
    )
    return int(proc.pid)


def try_warm_start_jailed(
    *,
    firecracker_bin: str,
    jailer_bin: str,
    vm_id: str,
    uid: int,
    gid: int,
    chroot_base: Path,
    log_path: Path,
    netns_path: str = "",
    label: str = "base",
) -> Optional[Tuple[int, Path]]:
    """Production warm start: jailer + snapshot load.

    Returns (pid, host_api_sock) or None if pool empty.
    Snapshot artifacts are staged into the jail so paths are valid post-chroot.
    """
    if not warm_pool_enabled():
        return None
    if not jailer_bin or not Path(jailer_bin).is_file() and not shutil.which(jailer_bin):
        logger.warning("warm_jailed: jailer missing")
        return None
    pool = get_warm_pool()
    arts = pool.get(label) or pool.get(os.environ.get("TBE_FC_SNAPSHOT_LABEL") or "base")
    if arts is None:
        logger.info("warm_jailed: no snapshot for label=%s", label)
        return None

    chroot_base = Path(chroot_base)
    chroot_base.mkdir(parents=True, exist_ok=True)
    jail_root = chroot_base / vm_id / "root"
    jail_root.mkdir(parents=True, exist_ok=True)
    run_dir = jail_root / "run"
    snap_dir = jail_root / "snapshot"
    run_dir.mkdir(parents=True, exist_ok=True)
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Stage snapshot into jail — hardlink/reflink first (avoid multi-GB copy)
    snap_dst = snap_dir / "snapshot"
    mem_dst = snap_dir / "mem"
    t_stage = time.perf_counter()
    try:
        m1 = fast_link_or_copy(arts.snapshot_path, snap_dst)
        m2 = fast_link_or_copy(arts.mem_path, mem_dst)
        for pth in (snap_dst, mem_dst, run_dir, snap_dir, jail_root):
            try:
                os.chown(pth, uid, gid)
            except OSError:
                pass
        logger.info(
            "warm_jailed stage methods snap=%s mem=%s elapsed_ms=%.0f",
            m1, m2, (time.perf_counter() - t_stage) * 1000,
        )
    except OSError as exc:
        logger.error("warm_jailed stage failed: %s", type(exc).__name__)
        return None

    staged = SnapshotArtifacts(snapshot_path=snap_dst, mem_path=mem_dst, label=arts.label)

    cmd = [
        jailer_bin,
        "--id", vm_id,
        "--exec-file", firecracker_bin,
        "--uid", str(uid),
        "--gid", str(gid),
        "--chroot-base-dir", str(chroot_base),
        "--daemonize",
        "--new-pid-ns",
    ]
    if netns_path:
        cmd.extend(["--netns", netns_path])
    cmd.extend(["--", "--api-sock", "/run/firecracker.socket"])

    log_f = open(log_path, "a")
    try:
        proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
    except Exception:
        log_f.close()
        raise

    host_sock = jail_root / "run" / "firecracker.socket"
    for _ in range(150):
        if host_sock.exists():
            break
        time.sleep(0.1)
    else:
        try:
            proc.kill()
        except OSError:
            pass
        raise RuntimeError("warm_jailed_sock_timeout")

    try:
        # Paths inside jail namespace as Firecracker sees them
        jail_arts = SnapshotArtifacts(
            snapshot_path=Path("/snapshot/snapshot"),
            mem_path=Path("/snapshot/mem"),
            label=arts.label,
        )
        # Host-visible files for readahead (same inode if hardlinked)
        if snap_dst.is_file():
            from .fc_snapshot import readahead_file
            readahead_file(snap_dst)
            readahead_file(mem_dst)
        metrics = load_and_resume(host_sock, jail_arts) or {}
        logger.info("warm_jailed load_ms=%s", metrics.get("load_ms"))
    except Exception:
        try:
            proc.kill()
        except OSError:
            pass
        raise

    # Daemonized jailer parent may exit; resolve real pid from firecracker.pid if present
    pid = int(proc.pid)
    for cand in (
        jail_root / "run" / "firecracker.pid",
        chroot_base / vm_id / "firecracker.pid",
    ):
        if cand.is_file():
            try:
                pid = int(cand.read_text().strip().split()[0])
                break
            except (ValueError, OSError):
                pass
    logger.info("warm_jailed resumed label=%s pid=%s sock=%s", arts.label, pid, host_sock)
    return pid, host_sock
