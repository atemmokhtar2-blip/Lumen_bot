"""Build IR — Intermediate Representation for generation control plane.

IR is NOT a translator. It is the validated contract between:
  User intent  →  Core  →  Execution engines (catalog | cline | hybrid)

Planning stays outside generation: IR is accepted/rejected before any write.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EngineMode(str, Enum):
    """Which execution path Core selects after IR validation."""

    CATALOG = "catalog"   # deterministic spec_core only
    HYBRID = "hybrid"     # catalog compose + constrained assist for gaps
    CLINE = "cline"       # general agent execution under policies
    INFINITE = "infinite" # atomic DAG / DynamicBotSpec rule engine


class IRStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class AcceptanceCriterion:
    id: str
    description: str
    kind: str = "command"  # command | flow | smoke | custom

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BuildIR:
    """Canonical handoff object for all generation engines.

    Core owns this. Engines consume it; they do not invent product policy.
    """

    original_text: str
    spec_request: str
    purpose: str = ""
    preferred_keys: list[str] = field(default_factory=list)
    capabilities_matched: list[str] = field(default_factory=list)
    capabilities_gap: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    acceptance: list[AcceptanceCriterion] = field(default_factory=list)
    engine_mode: EngineMode = EngineMode.CATALOG
    confidence: float = 0.0
    model: str = "rules"
    status: IRStatus = IRStatus.DRAFT
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    user_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["engine_mode"] = self.engine_mode.value if isinstance(self.engine_mode, EngineMode) else str(self.engine_mode)
        d["status"] = self.status.value if isinstance(self.status, IRStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "BuildIR":
        data = dict(data or {})
        mode_raw = str(data.get("engine_mode") or "catalog").lower().strip()
        try:
            mode = EngineMode(mode_raw)
        except ValueError:
            # legacy aliases
            if mode_raw in {"ai_codegen", "spec_core"}:
                mode = EngineMode.CLINE if mode_raw == "ai_codegen" else EngineMode.CATALOG
            else:
                mode = EngineMode.CATALOG
        status_raw = str(data.get("status") or "draft").lower().strip()
        try:
            status = IRStatus(status_raw)
        except ValueError:
            status = IRStatus.DRAFT
        acc_raw = data.get("acceptance") or []
        acceptance: list[AcceptanceCriterion] = []
        for item in acc_raw:
            if isinstance(item, AcceptanceCriterion):
                acceptance.append(item)
            elif isinstance(item, dict) and item.get("id"):
                acceptance.append(
                    AcceptanceCriterion(
                        id=str(item["id"]),
                        description=str(item.get("description") or item["id"]),
                        kind=str(item.get("kind") or "command"),
                    )
                )
            elif isinstance(item, str) and item.strip():
                acceptance.append(AcceptanceCriterion(id=item.strip(), description=item.strip()))
        return cls(
            original_text=str(data.get("original_text") or "").strip(),
            spec_request=str(data.get("spec_request") or data.get("original_text") or "").strip(),
            purpose=str(data.get("purpose") or "").strip(),
            preferred_keys=[str(x).strip() for x in (data.get("preferred_keys") or []) if str(x).strip()],
            capabilities_matched=[str(x).strip() for x in (data.get("capabilities_matched") or []) if str(x).strip()],
            capabilities_gap=[str(x).strip() for x in (data.get("capabilities_gap") or []) if str(x).strip()],
            integrations=[str(x).strip() for x in (data.get("integrations") or []) if str(x).strip()],
            acceptance=acceptance,
            engine_mode=mode,
            confidence=float(data.get("confidence") or 0.0),
            model=str(data.get("model") or "rules"),
            status=status,
            notes=[str(x) for x in (data.get("notes") or []) if str(x).strip()],
            metadata=dict(data.get("metadata") or {}),
            user_id=int(data.get("user_id") or 0),
        )

    def non_core_keys(self) -> list[str]:
        core = {"start", "help", "lang", "language", "cancel"}
        return [k for k in self.preferred_keys if k not in core]


__all__ = [
    "AcceptanceCriterion",
    "BuildIR",
    "EngineMode",
    "IRStatus",
]
