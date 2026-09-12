"""Canonical bot entry-point discovery under a project root."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_entry_point(project_path: Path) -> Optional[Path]:
    project_path = Path(project_path)
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = project_path / name
        if p.is_file():
            return p
    for c in project_path.glob("*/main.py"):
        return c
    for c in project_path.glob("*/bot.py"):
        return c
    return None


# back-compat private name used by drivers
_find_entry_point = find_entry_point

__all__ = ["find_entry_point", "_find_entry_point"]
