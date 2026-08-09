"""
Formal Logic & DSL Engine pipeline.

text → DSL → Grounding → Inference → Structure Engine → [Gate] → Code (transpile) → Verify

HARD RULE — zero fixed domain templates:
  Every command, button, entity, rule, flow, and handler is derived from the
  user specification only. No shop/ticket/ecommerce/education packs.

Phase 1:
  Structure Engine materializes signature stubs + structure_manifest.json
  and runs Structure Gate before the (still monolithic) code transpile.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dsl.extractor import extract_dsl
from .inference.engine import InferenceResult, infer
from .structure.derive import derive_structure_plan
from .structure.gate import validate_structure_gate
from .structure.materialize import materialize_structure
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
    structure_plan: dict[str, Any] = field(default_factory=dict)
    structure_gate: dict[str, Any] = field(default_factory=dict)
    structure_files: list[str] = field(default_factory=list)
    structure_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "out_dir": self.out_dir,
            "files": list(self.files),
            "structure_files": list(self.structure_files),
            "structure_only": self.structure_only,
            "dsl_relations": self.dsl_relations,
            "dsl_operations": self.dsl_operations,
            "dsl_rules": self.dsl_rules,
            "verification": self.verification.to_dict() if self.verification else None,
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "structure_plan": dict(self.structure_plan or {}),
            "structure_gate": dict(self.structure_gate or {}),
        }


def _write_manifest(
    out_dir: Path,
    plan: Any,
    *,
    structure_files: list[str],
    code_files: list[str] | None = None,
    extra_notes: list[str] | None = None,
) -> None:
    notes = list(getattr(plan, "notes", None) or [])
    if extra_notes:
        notes.extend(extra_notes)
    payload = {
        "schema_version": getattr(plan, "schema_version", "0.1.0"),
        "bot_name": getattr(plan, "bot_name", "") or "",
        "command_names": list(getattr(plan, "command_names", None) or []),
        "entity_names": list(getattr(plan, "entity_names", None) or []),
        "button_labels": list(getattr(plan, "button_labels", None) or []),
        "flow_ids": list(getattr(plan, "flow_ids", None) or []),
        "files": [f.to_dict() for f in (getattr(plan, "files", None) or [])],
        "notes": notes,
        "structure_files": list(structure_files),
        "code_files": list(code_files or []),
    }
    (out_dir / "structure_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_structure_only(
    user_text: str,
    out_dir: str | Path,
    *,
    grounding_text: str | None = None,
) -> FormalBuildResult:
    """Phase 1 path: signature stubs + manifest + gate. No business logic."""
    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)

    plan = derive_structure_plan(
        inf,
        bot_name=getattr(program, "bot_name", "") or "",
    )
    structure_files = materialize_structure(plan, out_dir, overwrite=True)
    gate = validate_structure_gate(
        plan,
        out_dir=out_dir,
        require_materialized=True,
    )

    return FormalBuildResult(
        out_dir=str(out_dir),
        files=list(structure_files),
        structure_files=list(structure_files),
        structure_only=True,
        inference=inf,
        grounding=grounding,
        dsl_relations=len(program.relations),
        dsl_operations=len(program.operations),
        dsl_rules=len(getattr(program, "rules", []) or []),
        structure_plan=plan.to_dict(),
        structure_gate=gate.to_dict(),
        verification=None,
    )


def build_from_text(
    user_text: str,
    out_dir: str | Path,
    *,
    grounding_text: str | None = None,
) -> FormalBuildResult:
    """
    Full path with Phase 1 structure stage first, then transitional transpile.

    STRUCTURE_ONLY=1 → stop after structure.
    STRUCTURE_GATE_STRICT=1 → hard-stop if structure gate fails (no code).
    """
    if os.environ.get("STRUCTURE_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
        return build_structure_only(
            user_text, out_dir, grounding_text=grounding_text
        )

    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)

    plan = derive_structure_plan(
        inf,
        bot_name=getattr(program, "bot_name", "") or "",
    )
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    structure_files = materialize_structure(plan, root, overwrite=True)
    gate = validate_structure_gate(
        plan,
        out_dir=root,
        require_materialized=True,
    )

    strict = os.environ.get("STRUCTURE_GATE_STRICT", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if strict and not gate.ok:
        return FormalBuildResult(
            out_dir=str(root),
            files=list(structure_files),
            structure_files=list(structure_files),
            structure_only=True,
            inference=inf,
            grounding=grounding,
            dsl_relations=len(program.relations),
            dsl_operations=len(program.operations),
            dsl_rules=len(getattr(program, "rules", []) or []),
            structure_plan=plan.to_dict(),
            structure_gate=gate.to_dict(),
        )

    written = transpile(inf, root)
    plan2 = derive_structure_plan(
        inf,
        bot_name=getattr(program, "bot_name", "") or "",
        written_files=list(written or []) + list(structure_files),
    )
    _write_manifest(
        root,
        plan2,
        structure_files=list(structure_files),
        code_files=[str(p) for p in (written or [])],
        extra_notes=["phase1_structure_then_transpile"],
    )
    gate2 = validate_structure_gate(plan2, out_dir=root, require_materialized=False)
    report = verify_project(root)

    return FormalBuildResult(
        out_dir=str(root),
        files=written,
        structure_files=list(structure_files),
        structure_only=False,
        inference=inf,
        verification=report,
        grounding=grounding,
        dsl_relations=len(program.relations),
        dsl_operations=len(program.operations),
        dsl_rules=len(getattr(program, "rules", []) or []),
        structure_plan=plan2.to_dict(),
        structure_gate=gate2.to_dict(),
    )
