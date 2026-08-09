"""
Structure Gate — Phase 1 hard checks before Code Engine.

Rejects plans that are internally inconsistent or missing required bindings.
Does NOT invent missing domain features — only validates what the plan claims.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas.structure_plan import FileRole, StructureGateResult, StructurePlan


def validate_structure_gate(
    plan: StructurePlan,
    *,
    out_dir: str | Path | None = None,
    require_materialized: bool = False,
) -> StructureGateResult:
    """
    Hard gate for Phase 1.

    Errors (fail):
      - no entry file
      - duplicate paths
      - required path missing on disk when require_materialized
      - zero commands AND zero buttons AND zero entities (empty contract)

    Warnings:
      - command not bound to any handlers/entry file
      - entity not bound to models file
    """
    errors: list[str] = []
    warnings: list[str] = []

    paths = [f.path for f in plan.files]
    if len(paths) != len(set(paths)):
        errors.append("duplicate_paths_in_plan")

    entry = [f for f in plan.files if f.role == FileRole.ENTRY]
    if not entry:
        errors.append("missing_entry_file")

    handlers = [f for f in plan.files if f.role == FileRole.HANDLERS]
    models = [f for f in plan.files if f.role == FileRole.MODELS]

    if plan.command_names and not handlers and not entry:
        errors.append("commands_without_handler_or_entry")

    if plan.entity_names and not models:
        errors.append("entities_without_models_file")

    # Empty of all contract signals — structure alone is not enough to ship
    if not plan.command_names and not plan.button_labels and not plan.entity_names:
        warnings.append("empty_contract_surface")

    bound_cmds: set[str] = set()
    for f in plan.files:
        bound_cmds.update(f.binds_commands or [])
    for c in plan.command_names:
        if c not in bound_cmds:
            warnings.append(f"command_unbound:{c}")

    for e in plan.entity_names:
        if not any(e in (f.binds_entities or []) for f in plan.files):
            warnings.append(f"entity_unbound:{e}")

    if require_materialized and out_dir is not None:
        root = Path(out_dir)
        for f in plan.files:
            if not f.required:
                continue
            if not (root / f.path).exists():
                errors.append(f"missing_materialized:{f.path}")
        if not (root / "structure_manifest.json").exists():
            errors.append("missing_structure_manifest")

    return StructureGateResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def gate_to_dict(result: StructureGateResult) -> dict[str, Any]:
    return result.to_dict()
