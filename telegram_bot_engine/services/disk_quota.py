"""Per-user disk usage limits under OUTPUT_DIR/users (disk DoS mitigation)."""
from __future__ import annotations

import os
from pathlib import Path


def max_user_bytes() -> int:
    """Default 512 MiB per user sandbox; override with TBE_USER_DISK_MB."""
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


def enforce_user_quota(user_root: Path, *, extra_bytes: int = 0) -> None:
    """Raise RuntimeError if user sandbox exceeds quota (or would after extra_bytes)."""
    used = dir_size_bytes(user_root)
    limit = max_user_bytes()
    if used + max(0, extra_bytes) > limit:
        raise RuntimeError(
            f"disk_quota_exceeded: used={used} limit={limit} path={user_root}"
        )
