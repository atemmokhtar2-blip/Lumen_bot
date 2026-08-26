"""Structured evaluation record for production + bot-bench."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class EvalRunRecord:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    scenario_id: str = ""
    platform: str = "telegram"
    success: bool = False
    attempts: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["errors"] = list(self.errors)[:20]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalRunRecord":
        return cls(
            run_id=str(data.get("run_id") or uuid.uuid4().hex[:16]),
            scenario_id=str(data.get("scenario_id") or ""),
            platform=str(data.get("platform") or "telegram"),
            success=bool(data.get("success")),
            attempts=int(data.get("attempts") or 0),
            latency_s=float(data.get("latency_s") or 0.0),
            cost_usd=float(data.get("cost_usd") or 0.0),
            errors=[str(e) for e in (data.get("errors") or [])[:20]],
            metrics=dict(data.get("metrics") or {}),
            started_at=float(data.get("started_at") or time.time()),
            finished_at=float(data.get("finished_at") or 0.0),
        )


def finalize_record(rec: EvalRunRecord, *, success: bool, errors: list[str] | None = None) -> EvalRunRecord:
    rec.finished_at = time.time()
    rec.latency_s = max(0.0, rec.finished_at - rec.started_at)
    rec.success = bool(success)
    if errors:
        rec.errors = [str(e) for e in errors[:20]]
    return rec


__all__ = ["EvalRunRecord", "finalize_record"]
