"""Git = version boundary."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class GitBoundary:
    local_path: Path
    remote_url: Optional[str] = None
    default_branch: str = "main"
    is_dirty: bool = False
    @property
    def is_repo(self) -> bool:
        return (self.local_path / ".git").exists()
