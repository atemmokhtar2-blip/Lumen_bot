"""RunMetadata — diagnostics only. Never a stage output or source of truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RunMetadata:
    run_id: str = ""
    source: str = ""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    flags: Dict[str, bool] = field(default_factory=dict)
    timings_ms: Dict[str, float] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.flags[name] = value

    def record_timing(self, stage: str, duration_ms: float) -> None:
        self.timings_ms[stage] = float(duration_ms)

    def set_extra(self, key: str, value: Any) -> None:
        self.extra[key] = value

    def get_extra(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "flags": dict(self.flags),
            "timings_ms": dict(self.timings_ms),
            "extra": dict(self.extra),
        }


__all__ = ["RunMetadata"]
