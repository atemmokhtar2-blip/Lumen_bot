"""
End-to-end Formal Pipeline — Formal Logic & DSL Engine (active).

Text
  → Custom DSL (Relations & Operations)
  → Inference Engine (loops / decision trees / unique schemas)
  → Micro-Transpiler (statement-by-statement)
  → Formal Verification
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas.formal_spec import FormalBotSpec
from .schemas.program_contract import ProgramContract

logger = logging.getLogger(__name__)


@dataclass
class FormalPipelineResult:
    ok: bool
    spec: FormalBotSpec | None
    contract: ProgramContract | None
    project_path: Path | None
    gate: Any | None
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
    """
    Active path: Formal Logic & DSL Engine.
      text → Custom DSL → Inference → Micro-Transpiler → Formal Verification
    Old contract/codegen path is no longer the primary execution path.
    """
    t0 = time.perf_counter()
    stages: dict[str, Any] = {}
    errors: list[str] = []
    try:
        from .pipeline_formal import build_from_text

        result = build_from_text(user_text or "", output_dir)
        stages["dsl_relations"] = result.dsl_relations
        stages["dsl_operations"] = result.dsl_operations
        stages["files"] = len(result.files)
        stages["understanding"] = {"ok": True, "path": "dsl"}
        stages["codegen"] = {"ok": bool(result.verification and result.verification.ok)}
        if result.verification:
            stages["verification"] = result.verification.to_dict()
            stages["final_gate"] = {
                "ok": result.verification.ok,
                "errors": list(result.verification.errors),
                "warnings": list(result.verification.warnings),
            }
            if not result.verification.ok:
                errors.extend(result.verification.errors)
        ok = bool(result.verification and result.verification.ok)
        logger.info(
            "DSL formal pipeline done ok=%s relations=%s operations=%s path=%s",
            ok,
            result.dsl_relations,
            result.dsl_operations,
            result.out_dir,
        )
        return FormalPipelineResult(
            ok=ok,
            spec=None,
            contract=None,
            project_path=Path(result.out_dir) if result.out_dir else None,
            gate=None,
            seconds=time.perf_counter() - t0,
            stages=stages,
            errors=list(dict.fromkeys(errors)),
        )
    except Exception as e:
        errors.append(f"dsl_formal: {type(e).__name__}: {e}")
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


def run_pipeline(user_text: str, output_dir: str | Path):
    """
    Backward-compatible entry → (None|FormalBotSpec, Path, float).
    Active path is DSL formal engine.
    """
    result = run_formal_pipeline(user_text, output_dir)
    if result.project_path is None or not result.ok:
        raise RuntimeError(
            "formal pipeline failed: "
            + "; ".join(result.errors[:5] or ["unknown"])
        )
    return result.spec, result.project_path, result.seconds


def run_dsl_formal_pipeline(user_text: str, output_dir: str | Path) -> FormalPipelineResult:
    """
    Formal Logic & DSL Engine path:
      text → Custom DSL → Inference → Micro-Transpiler → Formal Verification
    """
    t0 = time.perf_counter()
    stages: dict[str, Any] = {}
    errors: list[str] = []
    try:
        from .pipeline_formal import build_from_text
        result = build_from_text(user_text or "", output_dir)
        stages["dsl_relations"] = result.dsl_relations
        stages["dsl_operations"] = result.dsl_operations
        stages["files"] = len(result.files)
        if result.verification:
            stages["verification"] = result.verification.to_dict()
            if not result.verification.ok:
                errors.extend(result.verification.errors)
        ok = bool(result.verification and result.verification.ok)
        return FormalPipelineResult(
            ok=ok,
            spec=None,
            contract=None,
            project_path=Path(result.out_dir),
            gate=None,
            seconds=time.perf_counter() - t0,
            stages=stages,
            errors=errors,
        )
    except Exception as e:
        errors.append(f"dsl_formal:{e}")
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

