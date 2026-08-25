"""Project registry — durable metadata for generated bots (control plane)."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectRecord:
    project_id: str
    user_id: int
    title: str
    engine_mode: str
    path: str | None = None
    ir_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = "created"  # created | delivered | failed
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectStore:
    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.getenv("CONTROL_PLANE_DIR") or "/tmp/lumen_control"
        self.root = Path(base) / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, project_id: str) -> Path:
        return self.root / f"{project_id}.json"

    def create(
        self,
        *,
        user_id: int,
        title: str,
        engine_mode: str,
        ir_snapshot: dict[str, Any] | None = None,
        path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        pid = uuid.uuid4().hex[:16]
        rec = ProjectRecord(
            project_id=pid,
            user_id=int(user_id or 0),
            title=(title or "bot")[:120],
            engine_mode=str(engine_mode or "catalog"),
            path=path,
            ir_snapshot=dict(ir_snapshot or {}),
            metadata=dict(metadata or {}),
        )
        self._path(pid).write_text(
            json.dumps(rec.to_dict(), ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
        return rec

    def update(self, project_id: str, **fields: Any) -> ProjectRecord | None:
        p = self._path(project_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        data.update({k: v for k, v in fields.items() if k != "project_id"})
        p.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        return ProjectRecord(**{k: data[k] for k in ProjectRecord.__dataclass_fields__})

    def get(self, project_id: str) -> ProjectRecord | None:
        p = self._path(project_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return ProjectRecord(**{k: data.get(k) for k in ProjectRecord.__dataclass_fields__})

    def list_for_user(self, user_id: int, limit: int = 50) -> list[ProjectRecord]:
        out: list[ProjectRecord] = []
        for f in sorted(self.root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if int(data.get("user_id") or 0) == int(user_id):
                    out.append(
                        ProjectRecord(**{k: data.get(k) for k in ProjectRecord.__dataclass_fields__})
                    )
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out


__all__ = ["ProjectRecord", "ProjectStore"]
