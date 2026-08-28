"""Resolve project path + entry point from UI state and session (real FS)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


_ENTRY_CANDIDATES = (
    "main.py",
    "bot.py",
    "app.py",
    "run.py",
    "__main__.py",
)


def resolve_project_path(project_ref: str, user_data: dict[str, Any] | None) -> Path | None:
    ud = user_data if isinstance(user_data, dict) else {}
    candidates: list[str] = []
    if project_ref:
        candidates.append(str(project_ref).strip())
    for key in ("pending_run", "pending_live_run", "pending_deploy", "pending_host"):
        blob = ud.get(key)
        if isinstance(blob, dict) and blob.get("project_path"):
            candidates.append(str(blob["project_path"]).strip())
    active = ud.get("active_repo") if isinstance(ud.get("active_repo"), dict) else {}
    if active.get("path"):
        candidates.append(str(active["path"]).strip())
    if ud.get("last_project_path"):
        candidates.append(str(ud["last_project_path"]).strip())

    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if p.is_dir():
            return p.resolve()
        if p.is_file():
            return p.parent.resolve()
    return None


def _norm_rel(s: str) -> str:
    return Path(s).as_posix().lstrip("./")


def resolve_entry_point(project_root: Path, preferred: str = "") -> str:
    if preferred:
        pref = Path(preferred)
        if not pref.is_absolute():
            cand = project_root / preferred
            if cand.is_file():
                return _norm_rel(preferred)
        elif pref.is_file():
            try:
                return _norm_rel(str(pref.relative_to(project_root)))
            except ValueError:
                return preferred
    for name in _ENTRY_CANDIDATES:
        if (project_root / name).is_file():
            return name
    try:
        for p in sorted(project_root.rglob("main.py"))[:8]:
            if any(x in p.parts for x in (".venv", "venv", "__pycache__", ".git")):
                continue
            try:
                return _norm_rel(str(p.relative_to(project_root)))
            except ValueError:
                return p.name
    except OSError:
        pass
    return preferred or "main.py"


def bind_active_repo(user_data: dict[str, Any], project_root: Path, *, entry: str = "") -> None:
    ep = entry or resolve_entry_point(project_root)
    user_data["active_repo"] = {
        "path": str(project_root),
        "url": "",
        "contract": {"entry_points": [{"path": ep}]},
        "from_ui_post": True,
    }
    user_data["last_project_path"] = str(project_root)
