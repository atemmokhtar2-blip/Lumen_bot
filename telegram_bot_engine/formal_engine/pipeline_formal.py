"""
Formal Logic & DSL Engine pipeline.

text → Custom DSL → Inference Engine → Micro-Transpiler → Formal Verification

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
from .verification.verifier import VerificationReport, verify_project


@dataclass
class FormalBuildResult:
    out_dir: str
    files: list[str] = field(default_factory=list)
    inference: InferenceResult | None = None
    verification: VerificationReport | None = None
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
        }


def build_from_text(user_text: str, out_dir: str | Path) -> FormalBuildResult:
    """
    Full formal path:
      1. Extract DSL (Relations & Operations)
      2. Infer loops / decision trees / unique schemas
      3. Micro-transpile statement-by-statement
      4. Formal verification
    """
    program = extract_dsl(user_text or "")
    inf = infer(program)
    written = transpile(inf, out_dir)
    report = verify_project(out_dir)
    return FormalBuildResult(
        out_dir=str(out_dir),
        files=written,
        inference=inf,
        verification=report,
        dsl_relations=len(program.relations),
        dsl_operations=len(program.operations),
        dsl_rules=len(getattr(program, 'rules', []) or []),
    )
