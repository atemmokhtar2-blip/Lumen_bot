"""Engine-owned UI state for Telegram surface (Batch 0 foundation).

The generation / hosting engines remain the source of truth for work.
This state only tracks *which UI phase* the user is in and which slots
are filled so the bot can render the next honest keyboard.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EngineUiPhase(str, Enum):
    """UI phases. Only HOME is rendered in Batch 0; others are reserved."""

    HOME = "home"
    IDLE = "idle"
    # Reserved for later batches (registered so callbacks cannot invent phases)
    GEN_TYPE = "gen_type"
    GEN_SLOTS = "gen_slots"
    GEN_CONFIRM = "gen_confirm"
    GENERATING = "generating"
    GEN_DONE = "gen_done"
    HOST_CONFIRM = "host_confirm"
    DASHBOARD = "dashboard"
    BILLING = "billing"
    HELP = "help"


class RuntimePlaneHint(str, Enum):
    """Mirrors runtime_planes without importing heavy modules at UI layer."""

    NONE = "none"
    TRIAL_CHAT = "trial_chat"
    PERMANENT_HOST = "permanent_host"


@dataclass
class UiButton:
    text: str
    action: str
    arg: str = ""


@dataclass
class EngineUiState:
    phase: EngineUiPhase = EngineUiPhase.HOME
    slots: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    project_ref: str = ""
    plane: RuntimePlaneHint = RuntimePlaneHint.NONE
    last_action: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "slots": dict(self.slots),
            "missing": list(self.missing),
            "project_ref": self.project_ref,
            "plane": self.plane.value,
            "last_action": self.last_action,
            "version": int(self.version),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "EngineUiState":
        if not isinstance(raw, dict):
            return cls()
        phase_raw = str(raw.get("phase") or EngineUiPhase.HOME.value)
        try:
            phase = EngineUiPhase(phase_raw)
        except ValueError:
            phase = EngineUiPhase.HOME
        plane_raw = str(raw.get("plane") or RuntimePlaneHint.NONE.value)
        try:
            plane = RuntimePlaneHint(plane_raw)
        except ValueError:
            plane = RuntimePlaneHint.NONE
        slots = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
        missing = raw.get("missing") if isinstance(raw.get("missing"), list) else []
        return cls(
            phase=phase,
            slots={str(k): str(v) for k, v in slots.items() if k is not None},
            missing=[str(x) for x in missing],
            project_ref=str(raw.get("project_ref") or "")[:500],
            plane=plane,
            last_action=str(raw.get("last_action") or "")[:80],
            version=int(raw.get("version") or 1),
        )


def state_summary_ar(state: EngineUiState) -> str:
    """Short Arabic line for debugging / status — not a full UX screen."""
    return (
        f"واجهة المحرك | مرحلة: `{state.phase.value}`"
        + (f" | مشروع: `{state.project_ref}`" if state.project_ref else "")
    )
