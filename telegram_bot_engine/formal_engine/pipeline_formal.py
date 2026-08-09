"""
Formal Logic & DSL Engine pipeline.

text → Custom DSL → Grounding gate → Inference → Micro-Transpiler → Formal Verification

HARD RULE — zero fixed domain templates:
  Every command, button, entity, rule, flow, and handler is derived from the
  user specification only. No shop/ticket/ecommerce/education packs, no canned
  skeletons, no default domain command lists. Structural helpers (e.g. ensuring
  /start and /help exist) are the only allowed minima.

Phase 0:
  After inference (+ optional transpile), a StructurePlan is derived for
  observation/metadata only. Structure and Code engines are not split yet;
  transpile still writes full files (stub_kind=WIRED).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dsl.extractor import extract_dsl
from .inference.engine import InferenceResult, infer
from .structure.derive import derive_structure_plan, validate_structure_plan_basic
from .transpiler.micro import transpile
from .verification.grounding_gate import GroundingReport, apply_grounding_gate
from .verification.verifier import VerificationReport, verify_project


@dataclass
class FormalBuildResult:
    out_dir: str
    files: list[str] = field(default_factory=list)
    inference: InferenceResult | None = None
    verification: VerificationReport | None = None
    grounding: GroundingReport | None = None
    dsl_relations: int = 0
    dsl_operations: int = 0
    dsl_rules: int = 0
    # Phase 0 — structure contract (observation; does not alter written files)
    structure_plan: dict[str, Any] = field(default_factory=dict)
    structure_gate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "out_dir": self.out_dir,
            "files": list(self.files),
            "dsl_relations": self.dsl_relations,
            "dsl_operations": self.dsl_operations,
            "dsl_rules": self.dsl_rules,
            "verification": self.verification.to_dict() if self.verification else None,
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "structure_plan": dict(self.structure_plan or {}),
            "structure_gate": dict(self.structure_gate or {}),
        }


def build_from_text(
    user_text: str,
    out_dir: str | Path,
    *,
    grounding_text: str | None = None,
) -> FormalBuildResult:
    """
    Full formal path:
      1. Extract DSL (Relations & Operations)
      2. Grounding gate — drop anything not present in grounding_text
      3. Infer loops / decision trees / unique schemas
      4. Derive StructurePlan (Phase 0 observation)
      5. Micro-transpile statement-by-statement (still monolithic)
      6. Formal verification
    """
    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)

    # Phase 0: structure plan from grounded IR only (no domain packs)
    plan = derive_structure_plan(inf, bot_name=getattr(program, "bot_name", "") or "")
    gate = validate_structure_plan_basic(plan)

    written = transpile(inf, out_dir)
    report = verify_project(out_dir)

    # Re-derive with written paths recorded (still observation only)
    plan = derive_structure_plan(
        inf,
        bot_name=getattr(program, "bot_name", "") or "",
        written_files=list(written or []),
    )
    gate = validate_structure_plan_basic(plan)

    return FormalBuildResult(
        out_dir=str(out_dir),
        files=written,
        inference=inf,
        verification=report,
        grounding=grounding,
        dsl_relations=len(program.relations),
        dsl_operations=len(program.operations),
        dsl_rules=len(getattr(program, "rules", []) or []),
        structure_plan=plan.to_dict(),
        structure_gate=gate.to_dict(),
    )
