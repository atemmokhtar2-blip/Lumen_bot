"""
Code Engine — Phase 2.

Fills project files from grounded InferenceResult + StructurePlan.
Reuses formal emitters (no domain packs). Audits output for invented
commands/entities and dangerous patterns before writing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..inference.engine import InferenceResult
from ..schemas.code_fill import CodeEngineBatchResult, CodeFillRequest, CodeFillResult
from ..schemas.structure_plan import FileRole, PlannedFile, StructurePlan
from ..transpiler import micro as _micro
from .audit import audit_project_files, audit_source


def _allowed_commands(inf: InferenceResult, plan: StructurePlan | None) -> list[str]:
    names: list[str] = []
    if plan:
        names.extend(plan.command_names or [])
    for c in getattr(inf, "commands", None) or []:
        n = getattr(c, "name", None)
        if n and str(n) not in names:
            names.append(str(n).lstrip("/").lower())
    return names


def _allowed_entities(inf: InferenceResult, plan: StructurePlan | None) -> list[str]:
    names: list[str] = []
    if plan:
        names.extend(plan.entity_names or [])
    for e in getattr(inf, "entities", None) or []:
        n = getattr(e, "name", None)
        if n and str(n) not in names:
            names.append(str(n))
    for s in getattr(inf, "schemas", None) or []:
        n = getattr(s, "name", None)
        if n and str(n) not in names:
            names.append(str(n))
    return names


def _emit_for_rel(rel: str, inf: InferenceResult) -> str | None:
    """Map relative path → emitter. Returns None if not a known code file."""
    rel = rel.replace("\\", "/").replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    mapping = {
        "app/__init__.py": lambda: '"""app package"""\n',
        "app/models.py": lambda: _micro._emit_schema_module(inf),
        "app/store.py": lambda: _micro._emit_store_module(inf),
        "app/logic.py": lambda: _micro._emit_logic_module(inf),
        "app/tools.py": lambda: _emit_tools_fallback(inf),
        "app/services.py": lambda: _micro._emit_services_module(inf),
        "app/handlers.py": lambda: _micro._emit_handlers_module(inf),
        "app/container.py": lambda: _micro._emit_container(inf),
        "app/config.py": lambda: _micro._emit_config(inf),
        "main.py": lambda: _micro._emit_main(inf),
        "requirements.txt": lambda: _micro._emit_requirements(inf),
        ".env.example": lambda: _micro._emit_env(inf),
        "config.py": lambda: _micro._emit_config(inf),
    }
    fn = mapping.get(rel)
    if fn is None:
        base = rel.rsplit("/", 1)[-1]
        if base == ".env.example":
            fn = mapping.get(".env.example")
        elif base == "requirements.txt":
            fn = mapping.get("requirements.txt")
    if fn is None:
        return None
    return fn()


def _emit_tools_fallback(inf: InferenceResult) -> str:
    try:
        from ..transpiler.tools_emit import emit_tools_module
        return emit_tools_module(inf)
    except Exception:
        return '"""tools — none declared in user contract."""\n'


def fill_file(
    request: CodeFillRequest,
    inf: InferenceResult,
) -> CodeFillResult:
    """Fill a single planned file from formal IR; audit against contract."""
    rel = request.target.path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith("./"):
        rel = rel[2:]

    try:
        content = _emit_for_rel(rel, inf)
        if content is None:
            # Unknown path: leave empty structural comment — do not invent domain code
            content = f'"""Reserved path {rel} — no formal emitter."""\n'

        allowed_c = set(_allowed_commands(inf, request.plan))
        allowed_e = set(_allowed_entities(inf, request.plan))
        errs = audit_source(
            content,
            path=rel,
            allowed_commands=allowed_c,
            allowed_entities=allowed_e,
        )
        used_cmds = [
            c
            for c in allowed_c
            if f"/{c}" in content or f"'{c}'" in content or f'"{c}"' in content or f"cmd_{c}" in content
        ]
        used_ents = [
            e
            for e in allowed_e
            if e in content or (e and e[0].upper() + e[1:] in content)
        ]
        return CodeFillResult(
            path=rel,
            content=content if not content.endswith("\n") else content,
            ok=len(errs) == 0,
            errors=errs,
            used_commands=used_cmds,
            used_entities=used_ents,
        )
    except Exception as exc:
        return CodeFillResult(
            path=rel,
            content="",
            ok=False,
            errors=[f"emit_error:{type(exc).__name__}:{exc}"[:300]],
        )


def fill_project(
    inf: InferenceResult,
    out_dir: str | Path,
    *,
    plan: StructurePlan | None = None,
    strict_audit: bool | None = None,
) -> CodeEngineBatchResult:
    """
    Emit all code files for the project from formal IR.

    Writes only after per-file audit (when strict). Always writes when not strict
    but aggregates errors for the caller.
    """
    if strict_audit is None:
        strict_audit = os.environ.get("CODE_GATE_STRICT", "1").strip().lower() in {
            "1", "true", "yes", "on",
        }

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Canonical file set from formal emitters (contract-driven content)
    rel_files = [
        "app/__init__.py",
        "app/models.py",
        "app/store.py",
        "app/logic.py",
        "app/tools.py",
        "app/services.py",
        "app/handlers.py",
        "app/container.py",
        "app/config.py",
        "main.py",
        "requirements.txt",
        ".env.example",
    ]

    if plan is None:
        from ..structure.derive import derive_structure_plan
        plan = derive_structure_plan(inf)

    results: list[CodeFillResult] = []
    pending: dict[str, str] = {}
    all_errors: list[str] = []

    for rel in rel_files:
        target = PlannedFile(path=rel, role=_role_for(rel))
        req = CodeFillRequest(
            plan=plan,
            target=target,
            commands=[{"name": n} for n in (plan.command_names or [])],
            entities=[{"name": n} for n in (plan.entity_names or [])],
            buttons=[{"label": n} for n in (plan.button_labels or [])],
            flows=[{"id": n} for n in (plan.flow_ids or [])],
        )
        res = fill_file(req, inf)
        results.append(res)
        all_errors.extend(res.errors)
        if res.ok or not strict_audit:
            if res.content:
                pending[rel] = res.content

    # Project-level audit on the batch
    batch_errs = audit_project_files(
        pending,
        allowed_commands=_allowed_commands(inf, plan),
        allowed_entities=_allowed_entities(inf, plan),
    )
    all_errors.extend(batch_errs)

    if strict_audit and all_errors:
        return CodeEngineBatchResult(
            files=results,
            ok=False,
            errors=list(dict.fromkeys(all_errors)),
        )

    written_results: list[CodeFillResult] = []
    for rel, content in pending.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = content.replace("\r\n", "\n").rstrip() + "\n"
        path.write_text(text, encoding="utf-8")
        written_results.append(
            CodeFillResult(path=rel, content=text, ok=True, errors=[])
        )

    return CodeEngineBatchResult(
        files=written_results or results,
        ok=len(all_errors) == 0,
        errors=list(dict.fromkeys(all_errors)),
    )


def _role_for(rel: str) -> FileRole:
    rel = rel.replace("\\", "/")
    if rel.endswith("main.py"):
        return FileRole.ENTRY
    if "models" in rel:
        return FileRole.MODELS
    if "handler" in rel:
        return FileRole.HANDLERS
    if "config" in rel:
        return FileRole.CONFIG
    if "service" in rel:
        return FileRole.SERVICES
    if rel.endswith("requirements.txt"):
        return FileRole.REQUIREMENTS
    if rel.endswith(".env.example"):
        return FileRole.ENV_EXAMPLE
    return FileRole.OTHER
