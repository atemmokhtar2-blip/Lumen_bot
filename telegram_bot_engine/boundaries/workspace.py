"""Workspace = place of edit."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class WorkspaceHandle:
    root: Path
    project_id: Optional[str] = None
    label: str = ""
    def resolve(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)
    def exists(self) -> bool:
        return self.root.exists()
