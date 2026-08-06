"""
Spec-Driven Pipeline — the new generation path.

  user text
    → SpecTranslator v2 (AI: 4-pass translate → RichSpec JSON)
    → ContractBuilder (RichSpec → InferenceResult + ProgramContract)
    → SpecDrivenTranspiler (generate code from spec)
    → Formal Verification (syntax + handlers + compile)

This pipeline consumes RichSpec directly — NO lossy text round-trip.
Every behavioral decision comes from the AI's structured spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas.rich_spec import RichSpec, validate_rich_spec
from ..verification.verifier import VerificationReport, verify_project
from .contract_builder import build_from_spec, SpecBuildResult
from .spec_transpiler import transpile_spec


@dataclass
class SpecBuildResult2:
    """Result of the spec-driven build pipeline."""
    out_dir: str
    files: list[str] = field(default_factory=list)
    spec: RichSpec | None = None
    contract_ok: bool = False
    contract_errors: list[str] = field(default_factory=list)
    contract_warnings: list[str] = field(default_factory=list)
    verification: VerificationReport | None = None
    spec_validation_warnings: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "out_dir": self.out_dir,
            "files": list(self.files),
            "contract_ok": self.contract_ok,
            "contract_errors": list(self.contract_errors),
            "contract_warnings": list(self.contract_warnings),
            "verification": self.verification.to_dict() if self.verification else None,
            "spec_validation_warnings": list(self.spec_validation_warnings),
            "commands": list(self.commands),
            "entities": list(self.entities),
            "engine_path": "spec_driven",
        }


def build_from_spec_pipeline(
    spec: RichSpec,
    out_dir: str | Path,
) -> SpecBuildResult2:
    """
    Spec-driven build: RichSpec → code → verification.
    This is the new primary pipeline.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Validate the spec
    spec_val = validate_rich_spec(spec)
    spec_warnings = list(spec_val.warnings)

    # Build contract + inference result
    build = build_from_spec(spec)

    # Transpile — generate code from the spec
    files = transpile_spec(spec, out_dir)

    # Verify
    report = verify_project(out_dir)

    return SpecBuildResult2(
        out_dir=str(out_dir),
        files=files,
        spec=spec,
        contract_ok=build.contract_ok,
        contract_errors=list(build.contract_errors),
        contract_warnings=list(build.contract_warnings),
        verification=report,
        spec_validation_warnings=spec_warnings,
        commands=spec.command_names(),
        entities=spec.entity_names(),
    )
