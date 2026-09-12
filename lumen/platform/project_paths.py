"""Canonical on-disk project path resolution (shared kernel).

bot, hosting, and engine must call this — never invent parallel resolvers.
Never invent a path: only existing directories are returned.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_on_disk_path(
    user_data: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
) -> str:
    """Return first existing directory among session/pending candidates, else "".

    Order: pending → pending_host/run → pending_repo_env → active_repo → last_* paths.
    """
    ud = dict(user_data or {})
    pending = dict(pending or {})
    pre = ud.get("pending_repo_env") if isinstance(ud.get("pending_repo_env"), dict) else {}
    ph = ud.get("pending_host") if isinstance(ud.get("pending_host"), dict) else {}
    pr = ud.get("pending_run") if isinstance(ud.get("pending_run"), dict) else {}
    ar = ud.get("active_repo") if isinstance(ud.get("active_repo"), dict) else {}
    candidates = [
        pending.get("project_path"),
        pending.get("path"),
        ph.get("project_path"),
        pr.get("project_path"),
        pre.get("path"),
        pre.get("project_path"),
        ar.get("path"),
        ud.get("last_project_path"),
        ud.get("last_clone_path"),
    ]
    for c in candidates:
        p = str(c or "").strip()
        if not p:
            continue
        try:
            root = Path(p).expanduser().resolve()
        except Exception:
            continue
        if root.is_dir():
            return str(root)
    return ""


__all__ = ["resolve_on_disk_path"]
