"""Firecracker snapshot create/load — real VMM API (PUT /snapshot/*).

Performance-oriented path (E2B / Lambda-class resume):
  1) Boot base microVM to guest-ready
  2) PATCH /vm state=Paused
  3) PUT /snapshot/create (Full base, optional Diff thereafter)
  4) Fresh VMM → PUT /snapshot/load with File backend + resume_vm
  5) Staging uses hardlink → reflink → copy (never full copy when avoidable)
  6) Optional posix_fadvise readahead on mem file before load

This module does not fake snapshots; without a live API socket it fails closed.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _api_put(sock_path: Path, path: str, body: dict, *, timeout: float = 60.0) -> None:
    payload = json.dumps(body).encode("utf-8")
    req = (
        f"PUT {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Accept: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"\r\n"
    ).encode("utf-8") + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall(req)
        chunks: list[bytes] = []
        while True:
            try:
                data = s.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
            if b"\r\n\r\n" in b"".join(chunks):
                try:
                    s.settimeout(0.2)
                    while True:
                        more = s.recv(4096)
                        if not more:
                            break
                        chunks.append(more)
                except (socket.timeout, OSError):
                    pass
                break
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    if "HTTP/1.1 2" not in raw and "HTTP/1.0 2" not in raw:
        raise RuntimeError(f"fc_api_error:{path}:{raw[:300]}")


def _api_patch(sock_path: Path, path: str, body: dict, *, timeout: float = 30.0) -> None:
    payload = json.dumps(body).encode("utf-8")
    req = (
        f"PATCH {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Accept: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"\r\n"
    ).encode("utf-8") + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall(req)
        data = s.recv(8192)
    raw = data.decode("utf-8", errors="replace")
    if "HTTP/1.1 2" not in raw and "HTTP/1.0 2" not in raw:
        raise RuntimeError(f"fc_api_patch_error:{path}:{raw[:300]}")


@dataclass
class SnapshotArtifacts:
    snapshot_path: Path
    mem_path: Path
    label: str = ""

    def exists(self) -> bool:
        return self.snapshot_path.is_file() and self.mem_path.is_file()

    def size_bytes(self) -> int:
        n = 0
        for p in (self.snapshot_path, self.mem_path):
            try:
                n += p.stat().st_size
            except OSError:
                pass
        return n


def snapshot_root() -> Path:
    base = Path(
        os.environ.get("TBE_FC_SNAPSHOT_DIR")
        or os.path.join(os.environ.get("OUTPUT_DIR") or "/tmp", "fc_snapshots")
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def artifacts_for(label: str) -> SnapshotArtifacts:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80] or "base"
    d = snapshot_root() / safe
    d.mkdir(parents=True, exist_ok=True)
    return SnapshotArtifacts(
        snapshot_path=d / "vm.snap",
        mem_path=d / "vm.mem",
        label=safe,
    )


def pause_vm(sock: Path) -> None:
    _api_patch(sock, "/vm", {"state": "Paused"})


def resume_vm(sock: Path) -> None:
    _api_patch(sock, "/vm", {"state": "Resumed"})


def readahead_file(path: Path, *, max_mib: int = 512) -> None:
    """Advise kernel to page in snapshot mem file before Firecracker load."""
    if not _flag("TBE_FC_SNAPSHOT_READAHEAD", "1"):
        return
    if not path.is_file():
        return
    try:
        size = path.stat().st_size
        try:
            max_mib = int(os.environ.get("TBE_FC_SNAPSHOT_READAHEAD_MIB") or str(max_mib))
        except ValueError:
            pass
        cap = max_mib * 1024 * 1024
        length = min(size, cap) if cap > 0 else size
        if length <= 0:
            return
        fd = os.open(str(path), os.O_RDONLY)
        try:
            if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_WILLNEED"):
                os.posix_fadvise(fd, 0, length, os.POSIX_FADV_WILLNEED)
            else:
                chunk = 1024 * 1024
                left = length
                while left > 0:
                    n = os.read(fd, min(chunk, left))
                    if not n:
                        break
                    left -= len(n)
        finally:
            os.close(fd)
    except OSError as exc:
        logger.debug("readahead skipped: %s", type(exc).__name__)


def fast_link_or_copy(src: Path, dst: Path) -> str:
    """Stage snapshot file: hardlink → reflink → full copy."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            ss, ds = src.stat(), dst.stat()
            if ss.st_ino == ds.st_ino and ss.st_dev == ds.st_dev:
                return "hardlink-exists"
        except OSError:
            pass
        try:
            dst.unlink()
        except OSError:
            pass
    try:
        os.link(str(src), str(dst))
        return "hardlink"
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["cp", "--reflink=auto", str(src), str(dst)],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if r.returncode == 0 and dst.is_file():
            return "reflink"
    except (OSError, subprocess.TimeoutExpired):
        pass
    shutil.copy2(src, dst)
    return "copy"


def create_full_snapshot(sock: Path, arts: SnapshotArtifacts) -> SnapshotArtifacts:
    """Pause microVM and create Full snapshot (base template for warm pool)."""
    return _create_snapshot(sock, arts, snapshot_type="Full")


def create_diff_snapshot(sock: Path, arts: SnapshotArtifacts) -> SnapshotArtifacts:
    """Diff snapshot (dirty pages). Machine must have track_dirty_pages enabled."""
    return _create_snapshot(sock, arts, snapshot_type="Diff")


def _create_snapshot(
    sock: Path, arts: SnapshotArtifacts, *, snapshot_type: str
) -> SnapshotArtifacts:
    if not sock.exists() and not sock.is_symlink():
        raise RuntimeError(f"api_sock_missing:{sock}")
    arts.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    pause_vm(sock)
    body: dict[str, Any] = {
        "snapshot_type": snapshot_type,
        "snapshot_path": str(arts.snapshot_path.resolve()),
        "mem_file_path": str(arts.mem_path.resolve()),
        "sync_snapshot_files": _flag("TBE_FC_SNAPSHOT_SYNC", "1"),
    }
    _api_put(sock, "/snapshot/create", body, timeout=180.0)
    if not arts.exists():
        raise RuntimeError("snapshot_files_not_created")
    ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "fc snapshot created type=%s label=%s size_mib=%.1f elapsed_ms=%.0f",
        snapshot_type,
        arts.label,
        arts.size_bytes() / (1024 * 1024),
        ms,
    )
    return arts


def load_snapshot_payload(arts: SnapshotArtifacts, *, resume: bool = True) -> dict[str, Any]:
    if not arts.exists() and arts.snapshot_path.is_absolute():
        # jail-relative paths may not exist on host path namespace
        if not str(arts.snapshot_path).startswith("/"):
            raise RuntimeError(f"snapshot_missing:{arts.label}")
    if arts.snapshot_path.is_absolute() and arts.mem_path.is_absolute():
        if arts.snapshot_path.is_file() and arts.mem_path.is_file():
            pass
        elif not arts.exists():
            raise RuntimeError(f"snapshot_missing:{arts.label}")
    snap = str(arts.snapshot_path)
    mem = str(arts.mem_path)
    if arts.snapshot_path.is_absolute() and arts.snapshot_path.exists():
        snap = str(arts.snapshot_path.resolve())
    if arts.mem_path.is_absolute() and arts.mem_path.exists():
        mem = str(arts.mem_path.resolve())
    body: dict[str, Any] = {
        "snapshot_path": snap,
        "mem_backend": {
            "backend_type": "File",
            "backend_path": mem,
        },
        "resume_vm": bool(resume),
    }
    if _flag("TBE_FC_SNAPSHOT_ENABLE_DIFF_LOAD", "0"):
        body["enable_diff_snapshots"] = True
    return body


def load_and_resume(sock: Path, arts: SnapshotArtifacts) -> dict[str, float]:
    """Load snapshot into a fresh VMM. Returns timing metrics (ms)."""
    t0 = time.perf_counter()
    if arts.mem_path.is_file():
        readahead_file(arts.mem_path)
    t_read = time.perf_counter()
    body = load_snapshot_payload(arts, resume=True)
    _api_put(sock, "/snapshot/load", body, timeout=120.0)
    t_end = time.perf_counter()
    metrics = {
        "readahead_ms": (t_read - t0) * 1000,
        "load_ms": (t_end - t_read) * 1000,
        "total_ms": (t_end - t0) * 1000,
    }
    logger.info(
        "fc snapshot load label=%s readahead_ms=%.0f load_ms=%.0f",
        arts.label,
        metrics["readahead_ms"],
        metrics["load_ms"],
    )
    return metrics


class WarmPool:
    """In-process registry of base snapshot labels available for fast resume."""

    def __init__(self) -> None:
        self._labels: dict[str, SnapshotArtifacts] = {}

    def register(self, label: str, arts: Optional[SnapshotArtifacts] = None) -> SnapshotArtifacts:
        arts = arts or artifacts_for(label)
        if not arts.exists():
            raise RuntimeError(f"warm_pool_snapshot_missing:{label}")
        self._labels[label] = arts
        return arts

    def get(self, label: str = "base") -> Optional[SnapshotArtifacts]:
        if label in self._labels and self._labels[label].exists():
            return self._labels[label]
        arts = artifacts_for(label)
        if arts.exists():
            self._labels[label] = arts
            return arts
        return None

    def available(self, label: str = "base") -> bool:
        return self.get(label) is not None


_POOL = WarmPool()


def get_warm_pool() -> WarmPool:
    return _POOL
