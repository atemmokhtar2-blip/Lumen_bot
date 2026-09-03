"""Per-user disk usage limits under OUTPUT_DIR/users (disk DoS mitigation).

Pro plan users get 2 GB (2048 MB); non-Pro users get TBE_USER_DISK_MB (default 512 MB).
"""
from __future__ import annotations

import os
from pathlib import Path


def max_user_bytes(user_id: int = 0) -> int:
    """Disk quota for a user.  Pro → 2 GB; otherwise TBE_USER_DISK_MB (default 512 MB)."""
    # Pro plan entitlement (2 GB) takes priority over env default
    if user_id:
        try:
            from lumen.bot.ui.pro_plan_entitlement import resolve_plan_limits
            limits = resolve_plan_limits(int(user_id))
            return max(64, limits.disk_mb) * 1024 * 1024
        except Exception:
            pass  # fall through to env default
    try:
        mb = int(os.environ.get("TBE_USER_DISK_MB") or "512")
    except ValueError:
        mb = 512
    return max(32, mb) * 1024 * 1024


def dir_size_bytes(root: Path, *, limit_files: int = 50_000) -> int:
    total = 0
    n = 0
    root = Path(root)
    if not root.is_dir():
        return 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Do not follow symlinks
        dirnames[:] = [
            d for d in dirnames
            if not (Path(dirpath) / d).is_symlink()
        ]
        for name in filenames:
            n += 1
            if n > limit_files:
                return total
            fp = Path(dirpath) / name
            try:
                if fp.is_symlink():
                    continue
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def enforce_user_quota(user_root: Path, *, extra_bytes: int = 0, user_id: int = 0) -> None:
    """Raise RuntimeError if user sandbox exceeds quota (or would after extra_bytes).

    If ``user_id`` is provided, the quota is resolved from the Pro entitlement
    (2 GB for Pro, else TBE_USER_DISK_MB).
    """
    used = dir_size_bytes(user_root)
    limit = max_user_bytes(user_id) if user_id else max_user_bytes()
    if used + max(0, extra_bytes) > limit:
        raise RuntimeError(
            f"disk_quota_exceeded: used={used} limit={limit} path={user_root}"
        )
