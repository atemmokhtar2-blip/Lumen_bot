"""
Formal Logic & DSL Engine pipeline.

text → DSL → Grounding → Inference → Structure → Gate → Code Engine → Verify

HARD RULE — zero fixed domain templates.
Phase 2: Code Engine fills files from contract with security/contract audit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .code_engine.engine import fill_project
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
    code_engine: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)

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
            "code_engine": dict(self.code_engine or {}),
            "quality": dict(self.quality or {}),
        }


def _write_manifest(
    out_dir: Path,
    plan: Any,
    *,
    structure_files: list[str],
    code_files: list[str] | None = None,
    code_engine: dict[str, Any] | None = None,
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
        "code_engine": dict(code_engine or {}),
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
    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)
    inf.source_text = text
    plan = derive_structure_plan(inf, bot_name=getattr(program, "bot_name", "") or "")
    structure_files = materialize_structure(plan, out_dir, overwrite=True)
    gate = validate_structure_gate(plan, out_dir=out_dir, require_materialized=True)
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
    )


def build_from_text(
    user_text: str,
    out_dir: str | Path,
    *,
    grounding_text: str | None = None,
) -> FormalBuildResult:
    """
    Phase 2 pipeline:
      structure → structure gate → code engine (audited) → verify

    LEGACY_TRANSPILE=1 falls back to monolithic micro.transpile only.
    STRUCTURE_ONLY=1 stops after structure.
    STRUCTURE_GATE_STRICT=1 hard-stops if structure gate fails.
    CODE_GATE_STRICT=1 (default) refuses to write if audit finds invented surface/danger.
    """
    if os.environ.get("STRUCTURE_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
        return build_structure_only(user_text, out_dir, grounding_text=grounding_text)

    text = user_text or ""
    gate_src = grounding_text if grounding_text is not None else text
    program = extract_dsl(text)
    program, grounding = apply_grounding_gate(program, gate_src)
    inf = infer(program)
    inf.source_text = text

    plan = derive_structure_plan(inf, bot_name=getattr(program, "bot_name", "") or "")
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    structure_files = materialize_structure(plan, root, overwrite=True)
    gate = validate_structure_gate(plan, out_dir=root, require_materialized=True)

    strict_struct = os.environ.get("STRUCTURE_GATE_STRICT", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if strict_struct and not gate.ok:
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
            code_engine={"ok": False, "errors": ["structure_gate_blocked"]},
        )

    use_legacy = os.environ.get("LEGACY_TRANSPILE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }

    code_meta: dict[str, Any] = {}
    if use_legacy:
        written = transpile(inf, root)
        code_meta = {"path": "legacy_transpile", "ok": True, "errors": []}
    else:
        batch = fill_project(inf, root, plan=plan)
        code_meta = {
            "path": "code_engine",
            "ok": batch.ok,
            "errors": list(batch.errors),
            "files": [f.path for f in batch.files],
        }
        if not batch.ok and os.environ.get("CODE_GATE_STRICT", "1").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            # Keep structure stubs; do not claim success
            _write_manifest(
                root,
                plan,
                structure_files=list(structure_files),
                code_files=[],
                code_engine=code_meta,
                extra_notes=["phase2_code_gate_blocked"],
            )
            return FormalBuildResult(
                out_dir=str(root),
                files=list(structure_files),
                structure_files=list(structure_files),
                structure_only=False,
                inference=inf,
                grounding=grounding,
                dsl_relations=len(program.relations),
                dsl_operations=len(program.operations),
                dsl_rules=len(getattr(program, "rules", []) or []),
                structure_plan=plan.to_dict(),
                structure_gate=gate.to_dict(),
                code_engine=code_meta,
            )
        written = [str(root / f.path) for f in batch.files]

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
        code_engine=code_meta,
        extra_notes=["phase2_code_engine"],
    )
    gate2 = validate_structure_gate(plan2, out_dir=root, require_materialized=False)
    report = verify_project(root)

    from .verification.quality import measure_quality
    import py_compile
    compile_ok = True
    for py in root.rglob("*.py"):
        try:
            py_compile.compile(str(py), doraise=True)
        except Exception:
            compile_ok = False
            break
    q = measure_quality(
        root,
        expected_commands=list(plan2.command_names or []),
        expected_entities=list(plan2.entity_names or []),
        structure_gate_ok=bool(gate2.ok),
        code_engine_ok=bool(code_meta.get("ok", True)),
        verify_ok=bool(report.ok),
        compile_ok=compile_ok,
    )

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
        code_engine=code_meta,
        quality=q.to_dict(),
    )
