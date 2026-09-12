"""Canonical bot entry-point discovery under a project root."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

_DEFAULT_NAMES = ("main.py", "bot.py", "app.py", "run.py", "src/main.py")
_POLL_MARKERS = (
    "run_polling",
    "start_polling",
    "infinity_polling",
    "Application.builder",
)


def find_entry_point(
    project_path: Path,
    *,
    hints: Sequence[str] | None = None,
    scan_polling: bool = False,
    deep: bool = False,
) -> Optional[Path]:
    """Locate the primary Python entry under project_path.

    Order: explicit hints → common names → one-level */main.py|bot.py
    → optional content scan → optional deep rglob for main.py/bot.py.
    """
    project_path = Path(project_path)
    for h in hints or ():
        h = str(h or "").strip().replace("\\", "/")
        if not h:
            continue
        p = Path(h) if h.startswith("/") else project_path / h
        try:
            if p.is_file() and p.suffix == ".py":
                return p
        except Exception:
            continue
    for name in _DEFAULT_NAMES:
        p = project_path / name
        if p.is_file():
            return p
    for c in project_path.glob("*/main.py"):
        return c
    for c in project_path.glob("*/bot.py"):
        return c
    if scan_polling:
        try:
            for p in sorted(project_path.glob("*.py")):
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")[:8000]
                except Exception:
                    continue
                if any(m in text for m in _POLL_MARKERS):
                    return p
        except Exception:
            pass
    if deep:
        for name in ("main.py", "bot.py"):
            try:
                for p in project_path.rglob(name):
                    if any(x in p.parts for x in (".venv", "venv", "__pycache__", ".git")):
                        continue
                    return p
            except Exception:
                continue
    return None


def resolve_entry_rel(project_root: Path, preferred: str = "", *, scan_polling: bool = True) -> str:
    """Return entry path relative to project_root (posix), or preferred/main.py fallback."""
    root = Path(project_root).resolve()
    preferred = (preferred or "").strip().replace("\\", "/")
    found = find_entry_point(
        root,
        hints=[preferred] if preferred else None,
        scan_polling=scan_polling,
        deep=True,
    )
    if found is None:
        return preferred or "main.py"
    try:
        return found.resolve().relative_to(root).as_posix()
    except Exception:
        try:
            return found.relative_to(root).as_posix()
        except Exception:
            return preferred or found.name


_find_entry_point = find_entry_point
resolve_entry_point = resolve_entry_rel

__all__ = [
    "find_entry_point",
    "_find_entry_point",
    "resolve_entry_rel",
    "resolve_entry_point",
]
