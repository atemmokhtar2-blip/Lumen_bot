"""Discover common project runtime files (requirements, entry scripts)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


_REQ_NAMES = ("requirements.txt", "requirements-bot.txt", "reqs.txt")


def find_requirements(root: Path) -> Optional[Path]:
    root = Path(root)
    for name in _REQ_NAMES:
        p = root / name
        if p.is_file() or p.exists():
            return p
    return None


# back-compat
_find_requirements = find_requirements

__all__ = ["find_requirements", "_find_requirements"]
