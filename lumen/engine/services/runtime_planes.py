"""Two runtime planes — do not mix them.

═══════════════════════════════════════════════════════════════════
PERMANENT_HOST  — paid / long-running hosting (product surface)
TRIAL_CHAT      — short chat experience to try a generated bot
═══════════════════════════════════════════════════════════════════

PERMANENT_HOST
  Entry: HostService.start / pending_host / host_start
  Isolation: Firecracker only in production (select + market_gate)
  Lifecycle: long-running until user stops; persisted in hosting state
  Market: evaluate_market_gate required when commercial

TRIAL_CHAT
  Entry: LiveRunner / pending_run / live_run / smoke before ZIP
  Isolation: sandbox_runtime when available (same backends, ephemeral)
  Lifecycle: capped by LIVE_RUN_SECONDS (or plan); always stopped after
  Market: NOT commercial hosting — no HostService registry entry

Never route trial traffic through permanent HostService persistence.
Never weaken permanent hosting isolation for the sake of trial UX.
"""
from __future__ import annotations

from enum import Enum


class RuntimePlane(str, Enum):
    PERMANENT_HOST = "permanent_host"
    TRIAL_CHAT = "trial_chat"


def plane_label_ar(plane: RuntimePlane) -> str:
    if plane is RuntimePlane.PERMANENT_HOST:
        return "استضافة دائمة"
    return "تجربة مؤقتة في الشات"
