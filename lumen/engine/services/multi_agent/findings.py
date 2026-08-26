"""Structured critique findings — Critic → Repair → Worker (Phase A+)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CritiqueFinding:
    code: str
    severity: str  # error | warning
    message: str
    path: str = ""
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CritiqueFinding":
        return cls(
            code=str(d.get("code") or "unknown"),
            severity=str(d.get("severity") or "error"),
            message=str(d.get("message") or "")[:400],
            path=str(d.get("path") or "")[:200],
            fix_hint=str(d.get("fix_hint") or "")[:400],
        )


def findings_to_errors(findings: list[CritiqueFinding]) -> list[str]:
    out = []
    for f in findings:
        if f.severity != "error":
            continue
        loc = f" @{f.path}" if f.path else ""
        out.append(f"{f.code}{loc}: {f.message}")
    return out


def findings_to_repair_actions(findings: list[CritiqueFinding]) -> list[str]:
    actions = []
    for f in findings:
        if f.severity != "error":
            continue
        if f.fix_hint:
            actions.append(f"FIX[{f.code}]: {f.fix_hint}" + (f" (file:{f.path})" if f.path else ""))
        else:
            actions.append(f"RESOLVE[{f.code}]: {f.message}" + (f" (file:{f.path})" if f.path else ""))
    return actions[:20]


__all__ = [
    "CritiqueFinding",
    "findings_to_errors",
    "findings_to_repair_actions",
]
