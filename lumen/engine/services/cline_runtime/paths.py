"""Workspace root resolution for Cline tools."""
from __future__ import annotations

from pathlib import Path


def workspace_root(work_dir: str | Path) -> Path:
    return Path(work_dir).resolve()


_root = workspace_root

__all__ = ["workspace_root", "_root"]
