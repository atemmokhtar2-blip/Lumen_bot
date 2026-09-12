"""Resolve a real on-disk project path for trial/host token flows.

Never invent a path. Prefer pending → active_repo → last_project_path,
and only return directories that exist.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_session_project_path(
    pending: dict[str, Any] | None = None,
    user_data: dict[str, Any] | None = None,
) -> str:
    try:
        from lumen.platform.project_paths import resolve_on_disk_path
        return resolve_on_disk_path(user_data, pending)
    except Exception:
        pass
    pending = dict(pending or {})
    ud = dict(user_data or {})
    pre = ud.get("pending_repo_env") if isinstance(ud.get("pending_repo_env"), dict) else {}
    ph = ud.get("pending_host") if isinstance(ud.get("pending_host"), dict) else {}
    prun = ud.get("pending_run") if isinstance(ud.get("pending_run"), dict) else {}
    candidates = [
        pending.get("project_path"),
        pending.get("path"),
        ph.get("project_path"),
        prun.get("project_path"),
        pre.get("path"),
        pre.get("project_path"),
        (ud.get("active_repo") or {}).get("path") if isinstance(ud.get("active_repo"), dict) else None,
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


def wants_host_after_clone(text: str) -> bool:
    """User asked to pull AND run/host (not mere trial phrasing alone)."""
    t = (text or "").strip().lower()
    if not t:
        return False
    host_markers = (
        "استضف",
        "استضافة",
        "host",
        "deploy",
        "انشر",
        "نشر",
        "شغله",
        "شغّله",
        "شغله",
        "وشغله",
        "وشغّله",
        "شغل البوت",
        "شغّل البوت",
        "شغلوا",
    )
    pull_markers = ("اسحب", "سحب", "clone", "نزّل", "نزل", "جيب")
    has_pull = any(m in t for m in pull_markers) or "github.com" in t
    has_host = any(m in t for m in host_markers)
    return bool(has_pull and has_host)


__all__ = ["resolve_session_project_path", "wants_host_after_clone"]
