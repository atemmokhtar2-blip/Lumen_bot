"""Template launch policy (Phase 1) — fail-closed quotas.

Free tier (templates plane only):
  - max 3 concurrent running template instances per user
  - trial duration: 1..50 minutes (inclusive)
  - permanent TTL: 30 days

Does not call hosting; pure decision object for the future adapter.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from lumen.templates.models import TemplateInstance, TemplateInstanceStatus, TemplateLaunchMode

# Hard product caps (templates plane)
FREE_MAX_RUNNING_TEMPLATES = 3
TRIAL_MIN_MINUTES = 1
TRIAL_MAX_MINUTES = 50
PERMANENT_TTL_DAYS = 30

_ACTIVE = frozenset(
    {
        TemplateInstanceStatus.PREPARING,
        TemplateInstanceStatus.RUNNING,
    }
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    trial_minutes: int = 0
    expires_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "trial_minutes": self.trial_minutes,
            "expires_at": self.expires_at,
        }


def clamp_trial_minutes(minutes: int | float | None) -> int:
    try:
        m = int(minutes or 0)
    except (TypeError, ValueError):
        m = 0
    if m < TRIAL_MIN_MINUTES:
        return 0
    return max(TRIAL_MIN_MINUTES, min(TRIAL_MAX_MINUTES, m))


def count_active(instances: list[TemplateInstance] | tuple[TemplateInstance, ...]) -> int:
    n = 0
    now = time.time()
    for inst in instances or ():
        if inst.status not in _ACTIVE:
            continue
        # Expired by clock still counts as inactive for quota
        if inst.expires_at > 0 and inst.expires_at <= now:
            continue
        n += 1
    return n


def can_launch(
    *,
    mode: TemplateLaunchMode | str,
    instances: list[TemplateInstance] | tuple[TemplateInstance, ...] = (),
    trial_minutes: int | None = None,
    now: float | None = None,
    max_running: int = FREE_MAX_RUNNING_TEMPLATES,
) -> PolicyDecision:
    """Decide whether a user may launch another template instance."""
    ts = float(now if now is not None else time.time())
    if isinstance(mode, str):
        try:
            mode = TemplateLaunchMode(mode.strip().lower())
        except ValueError:
            return PolicyDecision(False, reason="invalid_mode")

    active = count_active(instances)
    if active >= max(1, int(max_running)):
        return PolicyDecision(
            False,
            reason=f"max_running_templates:{active}>={max_running}",
        )

    if mode is TemplateLaunchMode.TRIAL:
        mins = clamp_trial_minutes(trial_minutes)
        if mins <= 0:
            return PolicyDecision(
                False,
                reason=f"trial_minutes_out_of_range:1..{TRIAL_MAX_MINUTES}",
            )
        return PolicyDecision(
            True,
            reason="ok_trial",
            trial_minutes=mins,
            expires_at=ts + (mins * 60.0),
        )

    if mode is TemplateLaunchMode.PERMANENT:
        return PolicyDecision(
            True,
            reason="ok_permanent",
            trial_minutes=0,
            expires_at=ts + (PERMANENT_TTL_DAYS * 86400.0),
        )

    return PolicyDecision(False, reason="invalid_mode")


__all__ = [
    "FREE_MAX_RUNNING_TEMPLATES",
    "TRIAL_MIN_MINUTES",
    "TRIAL_MAX_MINUTES",
    "PERMANENT_TTL_DAYS",
    "PolicyDecision",
    "clamp_trial_minutes",
    "count_active",
    "can_launch",
]
