"""
Formal Logic & DSL Engine pipeline.

text → Custom DSL → Grounding gate → Inference → Micro-Transpiler → Formal Verification

HARD RULE — zero fixed domain templates:
  Every command, button, entity, rule, flow, and handler is derived from the
  user specification only. No shop/ticket/ecommerce/education packs, no canned
  skeletons, no default domain command lists. Structural helpers (e.g. ensuring
  /start and /help exist) are the only allowed minima.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dsl.extractor import extract_dsl
from .inference.engine import InferenceResult, infer
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "out_dir": self.out_dir,
            "files": list(self.files),
            "dsl_relations": self.dsl_relations,
            "dsl_operations": self.dsl_operations,
            "dsl_rules": self.dsl_rules,
            "verification": self.verification.to_dict() if self.verification else None,
            "grounding": self.grounding.to_dict() if self.grounding else None,
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
         (defaults to user_text; when Understanding-AI rewrites the spec,
         pass the ORIGINAL user words so AI cannot invent surface)
      3. Infer loops / decision trees / unique schemas
      4. Micro-transpile statement-by-statement
      5. Formal verification
    """
    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)
    written = transpile(inf, out_dir)
    report = verify_project(out_dir)
    return FormalBuildResult(
        out_dir=str(out_dir),
        files=written,
        inference=inf,
        verification=report,
        grounding=grounding,
        dsl_relations=len(program.relations),
        dsl_operations=len(program.operations),
        dsl_rules=len(getattr(program, "rules", []) or []),
    )
