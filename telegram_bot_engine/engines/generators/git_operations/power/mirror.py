"""Local bare mirror — read-only source of truth for templates/base repos."""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def mirror_root() -> Path:
    raw = (os.environ.get("TBE_GIT_MIRROR_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".capability_maestro"))
        p = (base / "git_mirrors").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _mirror_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def mirror_path_for(url: str) -> Path:
    return mirror_root() / f"{_mirror_id(url)}.git"


def _run(argv: list[str], *, cwd: Optional[Path] = None, timeout: int = 300) -> tuple[int, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        from telegram_bot_engine.services.secure_exec import run_git
        if not argv or argv[0] != "git":
            argv = ["git"] + list(argv or [])
        proc = run_git(list(argv), cwd=cwd, timeout=timeout)
        err = (proc.stderr or "") + (proc.stdout or "")
        return int(proc.returncode), err
    except Exception as exc:
        return 1, type(exc).__name__


def ensure_bare_mirror(url: str, *, token: Optional[str] = None) -> tuple[bool, Path, str]:
    """Fetch/update a local bare mirror for url. Mirror is never a worktree."""
    from ..smart_clone import _inject_token, normalize_and_validate_url

    clean, err = normalize_and_validate_url(url)
    if not clean:
        return False, Path(), err or "invalid_url"
    path = mirror_path_for(clean)
    fetch_url = _inject_token(clean, token) if token else clean

    if path.exists() and (path / "HEAD").exists():
        # update only — still remote fetch into mirror
        code, msg = _run(["git", "-C", str(path), "remote", "set-url", "origin", fetch_url])
        code, msg = _run(["git", "-C", str(path), "remote", "update", "--prune"], timeout=300)
        # scrub token from remote url
        _run(["git", "-C", str(path), "remote", "set-url", "origin", clean])
        if code != 0:
            logger.warning("mirror update failed: %s", msg[:200])
            # still usable offline
        return True, path, "mirror_updated" if code == 0 else "mirror_stale_ok"
    # fresh mirror clone
    if path.exists():
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    code, msg = _run(
        ["git", "clone", "--mirror", "--", fetch_url, str(path)],
        timeout=300,
    )
    if path.exists():
        _run(["git", "-C", str(path), "remote", "set-url", "origin", clean])
    if code != 0 or not (path / "HEAD").exists():
        return False, path, msg[:300] or "mirror_clone_failed"
    return True, path, "mirror_created"


def materialize_from_mirror(
    mirror: Path,
    dest: Path,
    *,
    branch: Optional[str] = None,
    depth: int = 1,
) -> tuple[bool, str]:
    """Create a disposable worktree/clone from local bare mirror (no network)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return False, "dest_exists"
    argv = ["git", "clone"]
    if depth and depth > 0:
        argv += [f"--depth={int(depth)}"]
    if branch:
        argv += ["--branch", branch, "--single-branch"]
    argv += ["--", str(mirror), str(dest)]
    code, msg = _run(argv, timeout=120)
    if code != 0 or not (dest / ".git").exists():
        return False, msg[:300] or "materialize_failed"
    return True, "materialized_from_mirror"
