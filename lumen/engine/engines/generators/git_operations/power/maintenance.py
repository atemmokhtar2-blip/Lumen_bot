"""Self-healing: collision-safe dirs (UUID), garbage collection."""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def unique_workdir(parent: Path, *, prefix: str = "work") -> Path:
    """
    Collision-proof directory under parent using UUID.
    Never overwrites an existing path.
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        name = f"{prefix}-{uuid.uuid4().hex[:12]}"
        dest = parent / name
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=False)
            return dest
    # astronomically unlikely
    dest = parent / f"{prefix}-{uuid.uuid4().hex}"
    dest.mkdir(parents=True, exist_ok=False)
    return dest


def prepare_dest_dir(parent: Path, preferred_name: str, *, prefix: str = "repo") -> Path:
    """If preferred name free, use it; else UUID suffix — never overwrite."""
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in (preferred_name or "repo"))[:60] or "repo"
    candidate = parent / safe
    if not candidate.exists():
        return candidate
    alt = parent / f"{safe}-{uuid.uuid4().hex[:8]}"
    logger.info("collision avoided: %s -> %s", candidate.name, alt.name)
    return alt


def git_gc(repo: Path, *, prune: bool = True) -> tuple[bool, str]:
    """Run git gc on a local repo (call from background jobs, not request path)."""
    repo = Path(repo)
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        return False, "not_git"
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    argv = ["git", "-C", str(repo), "gc"]
    if prune:
        argv.append("--prune=now")
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env, check=False)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "gc_failed")[:200]
        return True, "gc_ok"
    except Exception as exc:
        return False, type(exc).__name__


def gc_mirrors(mirror_root: Optional[Path] = None) -> dict:
    """Background-friendly: gc all bare mirrors under mirror root."""
    from .mirror import mirror_root as _mr
    root = Path(mirror_root) if mirror_root else _mr()
    stats = {"scanned": 0, "ok": 0, "failed": 0}
    if not root.is_dir():
        return stats
    for p in root.iterdir():
        if not p.is_dir():
            continue
        stats["scanned"] += 1
        ok, _ = git_gc(p)
        if ok:
            stats["ok"] += 1
        else:
            stats["failed"] += 1
    return stats
