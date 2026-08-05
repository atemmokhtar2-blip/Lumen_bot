"""
End-to-end Formal Pipeline (text-grounded, no domain templates).

Text
  → Understanding (FormalBotSpec + ProgramContract)
  → Planning (structural only)
  → Codegen (from ProgramContract, framework/layers aware)
  → FinalGate (static phases + fidelity + conversation flow)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas.formal_spec import FormalBotSpec
from .schemas.program_contract import ProgramContract
from .services.understanding_service.service import UnderstandingService
from .services.planning_service.service import PlanningService
from .services.codegen_service.service import generate_from_contract
from .services.static_dev_gate.final_gate import run_final_gate, FinalGateReport

logger = logging.getLogger(__name__)


@dataclass
class FormalPipelineResult:
    ok: bool
    spec: FormalBotSpec | None
    contract: ProgramContract | None
    project_path: Path | None
    gate: FinalGateReport | None
    seconds: float
    stages: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [
            f"{icon} *خط الأنابيب الرسمي*",
            f"• الزمن: `{self.seconds:.2f}s`",
        ]
        if self.project_path:
            lines.append(f"• المسار: `{self.project_path}`")
        if self.contract:
            lines.append(
                f"• أوامر: {len(self.contract.commands)} | "
                f"كيانات: {len(self.contract.entities)} | "
                f"خدمات: {len(self.contract.services)}"
            )
            fw = getattr(self.contract.architecture, "framework", "") or ""
            if fw:
                lines.append(f"• الإطار: `{fw}`")
        if self.gate:
            lines.append("")
            lines.append(self.gate.to_user_text())
        if self.errors:
            lines.append("")
            lines.append("*أخطاء المراحل:*")
            for e in self.errors[:15]:
                lines.append(f"• {e}")
        return "\n".join(lines)


def run_formal_pipeline(user_text: str, output_dir: str | Path) -> FormalPipelineResult:
    """Full deterministic pipeline with FinalGate."""
    t0 = time.perf_counter()
    stages: dict[str, Any] = {}
    errors: list[str] = []
    spec: FormalBotSpec | None = None
    contract: ProgramContract | None = None
    enriched: ProgramContract | None = None

    # 1. Understanding
    t1 = time.perf_counter()
    try:
        from .understanding.requirement_extractor import extract_formal_spec

        understanding = UnderstandingService()
        contract, validation = understanding.run(user_text or "")
        spec = extract_formal_spec(user_text or "")
        stages["understanding"] = {
            "ok": True,
            "ms": (time.perf_counter() - t1) * 1000,
            "commands": [c.name for c in contract.commands],
            "validation_ok": getattr(validation, "ok", True),
        }
    except Exception as e:
        errors.append(f"understanding: {type(e).__name__}: {e}")
        return FormalPipelineResult(
            ok=False,
            spec=None,
            contract=None,
            project_path=None,
            gate=None,
            seconds=time.perf_counter() - t0,
            stages=stages,
            errors=errors,
        )

    # 2. Planning (structural)
    t2 = time.perf_counter()
    try:
        enriched, plan_report = PlanningService().run(contract)
        stages["planning"] = {
            "ok": not plan_report.blocked,
            "ms": (time.perf_counter() - t2) * 1000,
            "decisions": list(plan_report.decisions)[:20],
            "readiness": plan_report.readiness_score,
        }
        if plan_report.blocked:
            errors.extend(list(plan_report.block_reasons or ["planning_blocked"]))
    except Exception as e:
        errors.append(f"planning: {type(e).__name__}: {e}")
        enriched = contract

    # 3. Codegen
    t3 = time.perf_counter()
    project_path: Path | None = None
    try:
        root = Path(output_dir)
        project_path, verify = generate_from_contract(enriched, root)
        stages["codegen"] = {
            "ok": bool(verify.get("ok")),
            "ms": (time.perf_counter() - t3) * 1000,
            "verify": {
                "errors": list(verify.get("errors") or []),
                "warnings": list(verify.get("warnings") or []),
            },
        }
        if not verify.get("ok"):
            errors.extend(list(verify.get("errors") or ["codegen_verify_failed"]))
    except Exception as e:
        errors.append(f"codegen: {type(e).__name__}: {e}")
        stages["codegen"] = {"ok": False, "ms": (time.perf_counter() - t3) * 1000}

    # 4. FinalGate
    gate: FinalGateReport | None = None
    t4 = time.perf_counter()
    if project_path is not None and project_path.exists():
        try:
            gate = run_final_gate(project_path)
            stages["final_gate"] = {
                "ok": gate.ok,
                "ms": (time.perf_counter() - t4) * 1000,
                "static_ok": gate.static_ok,
                "fidelity_ok": gate.fidelity_ok,
                "conversation_ok": gate.conversation_ok,
                "phases": gate.phases,
            }
            if not gate.ok:
                errors.extend(gate.errors[:20])
        except Exception as e:
            errors.append(f"final_gate: {type(e).__name__}: {e}")
            stages["final_gate"] = {"ok": False, "ms": (time.perf_counter() - t4) * 1000}
    else:
        errors.append("final_gate: no project path")

    total = time.perf_counter() - t0
    ok = (
        gate is not None
        and gate.ok
        and stages.get("codegen", {}).get("ok", False)
        and stages.get("understanding", {}).get("ok", False)
    )

    logger.info(
        "Formal pipeline done ok=%s total=%.0fms path=%s",
        ok,
        total * 1000,
        project_path,
    )
    return FormalPipelineResult(
        ok=ok,
        spec=spec,
        contract=enriched,
        project_path=project_path,
        gate=gate,
        seconds=total,
        stages=stages,
        errors=list(dict.fromkeys(errors)),
    )


def run_pipeline(user_text: str, output_dir: str | Path):
    """
    Backward-compatible entry → (FormalBotSpec, Path, float).
    Prefer run_formal_pipeline for full gate results.
    Never falls back to legacy template generators.
    """
    result = run_formal_pipeline(user_text, output_dir)
    if result.spec is None or result.project_path is None:
        raise RuntimeError(
            "formal pipeline failed: "
            + "; ".join(result.errors[:5] or ["unknown"])
        )
    return result.spec, result.project_path, result.seconds
