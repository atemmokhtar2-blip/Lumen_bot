"""Plan store — approved IR/plans before generation (control plane)."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PlanRecord:
    plan_id: str
    user_id: int
    ir: dict[str, Any]
    status: str = "draft"  # draft | approved | rejected | executed
    created_at: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlanStore:
    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.getenv("CONTROL_PLANE_DIR") or "/tmp/lumen_control"
        self.root = Path(base) / "plans"
        self.root.mkdir(parents=True, exist_ok=True)

    def save_draft(self, user_id: int, ir: dict[str, Any], notes: list[str] | None = None) -> PlanRecord:
        pid = uuid.uuid4().hex[:16]
        rec = PlanRecord(
            plan_id=pid,
            user_id=int(user_id or 0),
            ir=dict(ir or {}),
            status="draft",
            notes=list(notes or []),
        )
        self._write(rec)
        return rec

    def approve(self, plan_id: str) -> PlanRecord | None:
        rec = self.get(plan_id)
        if not rec:
            return None
        rec.status = "approved"
        self._write(rec)
        return rec

    def mark_executed(self, plan_id: str) -> PlanRecord | None:
        rec = self.get(plan_id)
        if not rec:
            return None
        rec.status = "executed"
        self._write(rec)
        return rec

    def get(self, plan_id: str) -> PlanRecord | None:
        p = self.root / f"{plan_id}.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return PlanRecord(**{k: data.get(k) for k in PlanRecord.__dataclass_fields__})

    def _write(self, rec: PlanRecord) -> None:
        path = self.root / f"{rec.plan_id}.json"
        path.write_text(json.dumps(rec.to_dict(), ensure_ascii=False, indent=0), encoding="utf-8")


__all__ = ["PlanRecord", "PlanStore"]
