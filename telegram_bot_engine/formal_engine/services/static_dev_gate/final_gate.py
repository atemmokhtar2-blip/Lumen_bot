"""
FinalGate — unified post-generation verdict.

Combines:
  1. Static quality pipeline (patterns → dataflow → contracts → symbolic → conversation_flow)
  2. FidelityGate (contract ↔ files coverage)
  3. Conversation flow errors already in pipeline

No domain templates. Blocks only on structural / fidelity / static errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .fidelity import check_project_fidelity, fidelity_as_dict
from .pipeline import run_pipeline, PipelineReport


@dataclass
class FinalGateReport:
    ok: bool
    static_ok: bool
    fidelity_ok: bool
    conversation_ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    phases: list[dict[str, Any]] = field(default_factory=list)
    pipeline: PipelineReport | None = None

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [
            f"{icon} *البوابة النهائية (Final Gate)*",
            f"• Static: {'✅' if self.static_ok else '❌'}",
            f"• Fidelity: {'✅' if self.fidelity_ok else '❌'}",
            f"• Conversation flow: {'✅' if self.conversation_ok else '❌'}",
            "",
        ]
        if self.coverage:
            lines.append("*تغطية:*")
            for k, v in self.coverage.items():
                lines.append(f"• `{k}`: {v}")
            lines.append("")
        if self.errors:
            lines.append("*أخطاء:*")
            for e in self.errors[:20]:
                lines.append(f"• {e}")
            lines.append("")
        if self.warnings:
            lines.append("*تحذيرات:*")
            for w in self.warnings[:12]:
                lines.append(f"• {w}")
        return "\n".join(lines)


def run_final_gate(project_dir: str | Path) -> FinalGateReport:
    root = Path(project_dir)
    errors: list[str] = []
    warnings: list[str] = []

    pipe = run_pipeline(str(root))
    static_ok = pipe.ok
    for f in pipe.static.findings:
        msg = f.message_ar or f.code
        if f.severity == "error":
            errors.append(msg)
        elif f.severity == "warning":
            warnings.append(msg)

    fid = check_project_fidelity(root)
    fidelity_ok = fid.ok
    for f in fid.errors:
        errors.append(f.message)
    for f in fid.warnings:
        warnings.append(f.message)

    cf = (pipe.meta or {}).get("conversation_flow") or {}
    conversation_ok = bool(cf.get("ok", True)) if cf else True
    if cf and not conversation_ok:
        for item in cf.get("findings") or []:
            if item.get("severity") == "error":
                msg = item.get("message") or item.get("code")
                if msg and msg not in errors:
                    errors.append(msg)

    phases = [
        {"name": p.name, "ok": p.ok, "detail": p.detail}
        for p in pipe.phases
    ]
    phases.append({
        "name": "fidelity",
        "ok": fidelity_ok,
        "detail": f"coverage={fid.coverage}",
    })

    coverage = {
        **(fid.coverage or {}),
        "static_errors": pipe.static.errors,
        "static_warnings": pipe.static.warnings,
        "conversation": cf.get("coverage") or {},
    }

    # de-dupe errors preserving order
    seen: set[str] = set()
    uniq_errors: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            uniq_errors.append(e)

    ok = static_ok and fidelity_ok and conversation_ok and not uniq_errors
    # if static already counted flow errors, ok tracks static_ok
    ok = fidelity_ok and static_ok

    return FinalGateReport(
        ok=ok,
        static_ok=static_ok,
        fidelity_ok=fidelity_ok,
        conversation_ok=conversation_ok,
        errors=uniq_errors,
        warnings=list(dict.fromkeys(warnings)),
        coverage=coverage,
        phases=phases,
        pipeline=pipe,
    )
