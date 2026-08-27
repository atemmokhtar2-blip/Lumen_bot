"""Firecracker snapshot create/load — real VMM API (PUT /snapshot/*).

Competitive path (E2B-class cold-start reduction):
  1) Boot base microVM to guest-ready
  2) PATCH /vm state=Paused
  3) PUT /snapshot/create {snapshot_path, mem_file_path, snapshot_type=Full}
  4) Later: fresh firecracker process → PUT /snapshot/load + resume_vm

This module does not fake snapshots; without a live API socket it fails closed.
"""
from __future__ import annotations

import json
import logging
import os
import socket
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
                # read a bit more for body
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


def create_full_snapshot(sock: Path, arts: SnapshotArtifacts) -> SnapshotArtifacts:
    """Pause microVM and create Full snapshot (requires live API socket)."""
    if not sock.exists() and not sock.is_symlink():
        raise RuntimeError(f"api_sock_missing:{sock}")
    pause_vm(sock)
    _api_put(
        sock,
        "/snapshot/create",
        {
            "snapshot_type": "Full",
            "snapshot_path": str(arts.snapshot_path.resolve()),
            "mem_file_path": str(arts.mem_path.resolve()),
            "sync_snapshot_files": True,
        },
        timeout=120.0,
    )
    if not arts.exists():
        raise RuntimeError("snapshot_files_not_created")
    logger.info(
        "fc snapshot created label=%s size_mib=%.1f",
        arts.label,
        arts.size_bytes() / (1024 * 1024),
    )
    return arts


def load_snapshot_payload(arts: SnapshotArtifacts, *, resume: bool = True) -> dict[str, Any]:
    """Body for PUT /snapshot/load on a fresh Firecracker process."""
    if not arts.exists():
        raise RuntimeError(f"snapshot_missing:{arts.label}")
    return {
        "snapshot_path": str(arts.snapshot_path.resolve()),
        "mem_backend": {
            "backend_type": "File",
            "backend_path": str(arts.mem_path.resolve()),
        },
        "resume_vm": bool(resume),
    }


def load_and_resume(sock: Path, arts: SnapshotArtifacts) -> None:
    """Load snapshot into a fresh VMM (no prior boot-source config)."""
    body = load_snapshot_payload(arts, resume=True)
    _api_put(sock, "/snapshot/load", body, timeout=120.0)


class WarmPool:
    """In-process registry of base snapshot labels available for fast resume.

    Operator pre-builds base snapshot once (kernel+rootfs+guest-ready).
    Runtime resumes and attaches per-tenant project/token drives separately
    when TBE_FC_WARM_POOL=1 and artifacts exist.
    """

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
