"""Deprecated — subscription plans removed. Credits-only billing."""
from __future__ import annotations

from enum import Enum


class PlanId(str, Enum):
    """Kept for import compatibility; always DEFAULT."""

    DEFAULT = "default"


class PlanTier(str, Enum):
    DEFAULT = "default"
