"""Pure policy for template launches — no I/O, no store, no Redis.

Free-tier product caps (templates plane only):
  - at most FREE_MAX_RUNNING concurrent active instances
  - trial minutes in [TRIAL_MIN_MINUTES, TRIAL_MAX_MINUTES]
  - permanent TTL = PERMANENT_TTL_DAYS

Fail-closed: any invalid input → denied.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from lumen.templates.models import TemplateInstance, TemplateLaunchMode

FREE_MAX_RUNNING = 3
TRIAL_MIN_MINUTES = 1
TRIAL_MAX_MINUTES = 50
PERMANENT_TTL_DAYS = 30


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Authoritative schedule produced by policy when allowed."""

    mode: TemplateLaunchMode
    trial_minutes: int
    expires_at: float
    max_running: int = FREE_MAX_RUNNING


@dataclass(frozen=True, slots=True)
class PolicyResult:
    allowed: bool
    reason: str
    plan: LaunchPlan | None = None

    @property
    def denied(self) -> bool:
        return not self.allowed


def clamp_trial_minutes(minutes: object) -> int:
    try:
        m = int(minutes)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if m < TRIAL_MIN_MINUTES:
        return 0
    return max(TRIAL_MIN_MINUTES, min(TRIAL_MAX_MINUTES, m))


def count_active(instances: Sequence[TemplateInstance], now: float) -> int:
    return sum(1 for i in instances if i.is_active(now))


def evaluate_launch(
    *,
    mode: TemplateLaunchMode | str,
    instances: Sequence[TemplateInstance],
    now: float,
    trial_minutes: object = None,
    max_running: int = FREE_MAX_RUNNING,
) -> PolicyResult:
    try:
        mode_e = mode if isinstance(mode, TemplateLaunchMode) else TemplateLaunchMode.parse(mode)
    except ValueError:
        return PolicyResult(False, "invalid_mode")

    cap = max(1, int(max_running))
    active = count_active(instances, now)
    if active >= cap:
        return PolicyResult(False, f"max_running_templates:{active}>={cap}")

    if mode_e is TemplateLaunchMode.TRIAL:
        mins = clamp_trial_minutes(trial_minutes)
        if mins <= 0:
            return PolicyResult(
                False,
                f"trial_minutes_out_of_range:{TRIAL_MIN_MINUTES}..{TRIAL_MAX_MINUTES}",
            )
        return PolicyResult(
            True,
            "ok_trial",
            LaunchPlan(
                mode=mode_e,
                trial_minutes=mins,
                expires_at=float(now) + mins * 60.0,
                max_running=cap,
            ),
        )

    if mode_e is TemplateLaunchMode.PERMANENT:
        return PolicyResult(
            True,
            "ok_permanent",
            LaunchPlan(
                mode=mode_e,
                trial_minutes=0,
                expires_at=float(now) + PERMANENT_TTL_DAYS * 86400.0,
                max_running=cap,
            ),
        )

    return PolicyResult(False, "invalid_mode")


# Back-compat aliases used by thin __init__
FREE_MAX_RUNNING_TEMPLATES = FREE_MAX_RUNNING
can_launch = evaluate_launch  # type: ignore[assignment]


__all__ = [
    "FREE_MAX_RUNNING",
    "FREE_MAX_RUNNING_TEMPLATES",
    "TRIAL_MIN_MINUTES",
    "TRIAL_MAX_MINUTES",
    "PERMANENT_TTL_DAYS",
    "LaunchPlan",
    "PolicyResult",
    "clamp_trial_minutes",
    "count_active",
    "evaluate_launch",
    "can_launch",
]
