"""Defensive tools — no fixed catalog. Tools come only from user/AI contract."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class DefensiveTool:
    id: str
    surface_forms: tuple[str, ...] = ()
    needs: str = "domain"
    description: str = ""

DEFENSIVE_TOOLS: tuple[DefensiveTool, ...] = ()

def resolve_defensive_tools(*texts: str) -> list[str]:
    return []
