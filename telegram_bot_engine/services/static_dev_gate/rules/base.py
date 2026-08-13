"""Rule protocol — add new checks without touching the engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import AnalysisContext, StaticFinding


@dataclass(frozen=True)
class RuleMeta:
    id: str
    description_ar: str
    default_enabled: bool = True
    tags: tuple[str, ...] = ()


class Rule(Protocol):
    meta: RuleMeta

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        ...
