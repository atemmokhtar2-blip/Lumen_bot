"""
Derive StructurePlan from formal IR — observation only in Phase 0.

Rules:
  - Command / entity / button / flow names come ONLY from the inference result
    (already grounded upstream). Never inject shop/ticket packs.
  - File paths are structural project layout (entry, config, models, …),
    not domain feature packs.
  - Phase 0 marks stub_kind=WIRED because the monolithic transpiler still
    writes full files; later phases switch to EMPTY/SIGNATURES.
"""

from __future__ import annotations

from typing import Any

from ..schemas.structure_plan import (
    FileRole,
    FileStubKind,
    PlannedFile,
    StructureGateResult,
    StructurePlan,
)


def _cmd_names(inf: Any) -> list[str]:
    out: list[str] = []
    for c in getattr(inf, "commands", None) or []:
        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
        if name:
            n = str(name).strip().lstrip("/").lower()
            if n and n not in out:
                out.append(n)
    return out


def _entity_names(inf: Any) -> list[str]:
    out: list[str] = []
    for e in getattr(inf, "entities", None) or []:
        name = getattr(e, "name", None) or (e.get("name") if isinstance(e, dict) else None)
        if name:
            n = str(name).strip()
            if n and n not in out:
                out.append(n)
    for s in getattr(inf, "schemas", None) or []:
        name = getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
        if name:
            n = str(name).strip()
            if n and n not in out:
                out.append(n)
    return out


def _button_labels(inf: Any) -> list[str]:
    out: list[str] = []
    for b in getattr(inf, "buttons", None) or []:
        lab = getattr(b, "label", None) or (b.get("label") if isinstance(b, dict) else None)
        if lab:
            s = str(lab).strip()
            if s and s not in out:
                out.append(s)
    return out


def _flow_ids(inf: Any) -> list[str]:
    out: list[str] = []
    for w in getattr(inf, "wizards", None) or []:
        if isinstance(w, dict):
            fid = str(w.get("id") or w.get("command") or "").strip()
        else:
            fid = str(getattr(w, "id", "") or getattr(w, "command", "") or "").strip()
        if fid and fid not in out:
            out.append(fid)
    return out


def _to_rel(path: str) -> str:
    """Normalize absolute/temp paths to project-relative."""
    rel = str(path or "").replace("\\", "/")
    if "/app/" in rel:
        return "app/" + rel.split("/app/", 1)[1]
    for name in ("main.py", "config.py", "requirements.txt", "README.md", ".env.example"):
        if rel.endswith("/" + name) or rel.endswith(name) and rel.count("/") <= 1:
            return name
    if rel.startswith("/") or rel.startswith("tmp/"):
        return rel.rsplit("/", 1)[-1]
    return rel.lstrip("./")


def derive_structure_plan(
    inf: Any,
    *,
    bot_name: str = "",
    written_files: list[str] | None = None,
) -> StructurePlan:
    """
    Build a StructurePlan from grounded inference (+ optional written paths).

    Does not create or modify any project files.
    """
    commands = _cmd_names(inf)
    entities = _entity_names(inf)
    buttons = _button_labels(inf)
    flows = _flow_ids(inf)

    files: list[PlannedFile] = [
        PlannedFile(
            path="main.py",
            role=FileRole.ENTRY,
            stub_kind=FileStubKind.WIRED,
            description="Application entry and handler registration",
            binds_commands=list(commands),
            binds_buttons=list(buttons),
            required=True,
        ),
        PlannedFile(
            path="config.py",
            role=FileRole.CONFIG,
            stub_kind=FileStubKind.WIRED,
            description="Typed configuration from environment",
            required=True,
        ),
        PlannedFile(
            path="app/models.py",
            role=FileRole.MODELS,
            stub_kind=FileStubKind.WIRED,
            description="Data models from user entities only",
            binds_entities=list(entities),
            required=bool(entities),
        ),
        PlannedFile(
            path="app/handlers.py",
            role=FileRole.HANDLERS,
            stub_kind=FileStubKind.WIRED,
            description="Command and callback handlers bound to user commands",
            binds_commands=list(commands),
            binds_flows=list(flows),
            binds_buttons=list(buttons),
            required=True,
        ),
        PlannedFile(
            path="requirements.txt",
            role=FileRole.REQUIREMENTS,
            stub_kind=FileStubKind.WIRED,
            description="Runtime dependencies",
            required=True,
        ),
        PlannedFile(
            path=".env.example",
            role=FileRole.ENV_EXAMPLE,
            stub_kind=FileStubKind.WIRED,
            description="Environment variable template (no secrets)",
            required=False,
        ),
        PlannedFile(
            path="README.md",
            role=FileRole.README,
            stub_kind=FileStubKind.WIRED,
            description="Project readme derived from contract names",
            required=False,
        ),
    ]

    known = {f.path for f in files}
    for p in written_files or []:
        rel = _to_rel(p)
        if not rel or rel in known:
            continue
        role = FileRole.OTHER
        if rel.endswith("models.py"):
            role = FileRole.MODELS
        elif "handler" in rel:
            role = FileRole.HANDLERS
        elif rel.endswith("config.py"):
            role = FileRole.CONFIG
        elif rel.endswith("main.py"):
            role = FileRole.ENTRY
        elif "service" in rel:
            role = FileRole.SERVICES
        files.append(
            PlannedFile(
                path=rel,
                role=role,
                stub_kind=FileStubKind.WIRED,
                description="Emitted by current monolithic transpile",
                required=False,
            )
        )
        known.add(rel)

    notes = [
        "phase0_observation_only",
        "no_domain_templates",
        "stub_kind_wired_until_structure_engine_splits",
    ]
    return StructurePlan(
        bot_name=(bot_name or "")[:64],
        files=files,
        command_names=commands,
        entity_names=entities,
        button_labels=buttons,
        flow_ids=flows,
        schema_version="0.1.0",
        notes=notes,
    )


def validate_structure_plan_basic(plan: StructurePlan) -> StructureGateResult:
    """
    Lightweight structural checks (Phase 0).
    Does not invent missing commands — only validates internal consistency.
    """
    errors: list[str] = []
    warnings: list[str] = []

    paths = [f.path for f in plan.files]
    if len(paths) != len(set(paths)):
        errors.append("duplicate_paths_in_plan")

    if not any(f.role == FileRole.ENTRY for f in plan.files):
        errors.append("missing_entry_file")

    bound: set[str] = set()
    for f in plan.files:
        bound.update(f.binds_commands)
    for c in plan.command_names:
        if c not in bound:
            warnings.append(f"command_unbound:{c}")

    for e in plan.entity_names:
        if not any(e in f.binds_entities for f in plan.files):
            warnings.append(f"entity_unbound:{e}")

    return StructureGateResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
