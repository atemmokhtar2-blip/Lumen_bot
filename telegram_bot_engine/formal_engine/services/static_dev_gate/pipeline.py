"""
Unified Static Analysis Pipeline — ordered composition of all phases.

Execution order (by dependency / cost):
  1. Syntax          — already enforced while building AnalysisContext
  2. AST Patterns    — structural, cheap, whole-module
  3. Control/Dataflow — CFG, nullability, resources, taint
  4. Contracts/Types — annotations, pre/post, type lattice
  5. Symbolic        — path-sensitive, bounded, most expensive

Each phase caches results on ModuleInfo so rules never recompute.
This module runs the analyzers explicitly in order, then the rule engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .context import build_context
from .engine import run_rules
from .models import AnalysisContext, StaticFinding, StaticReport
from .patterns import analyze_module_patterns
from .dataflow import analyze_module_flow
from .contracts import analyze_module_contracts
from .symbolic import analyze_module_symbolic
from .conversation_flow import analyze_conversation_flow


PHASE_ORDER = (
    "patterns",           # structural AST
    "dataflow",           # control + data flow
    "contracts",          # types / design by contract
    "symbolic",           # path-sensitive code
    "conversation_flow",  # state machine / NL flows
)


@dataclass
class PhaseResult:
    name: str
    ok: bool = True
    detail: str = ""
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class PipelineReport:
    """Unified report across all static phases."""

    ok: bool
    static: StaticReport
    phases: list[PhaseResult] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [
            f"{icon} *خط تحليل استاتيكي موحّد*",
            f"• ملفات: {self.static.files_checked} | أخطاء: {self.static.errors} | "
            f"تحذيرات: {self.static.warnings} | معلومات: {self.static.infos}",
            "",
            "*المراحل (بالترتيب):*",
        ]
        for p in self.phases:
            mark = "✅" if p.ok else "⚠️"
            extra = f" — {p.detail}" if p.detail else ""
            lines.append(f"{mark} `{p.name}`{extra}")
        lines.append("")
        lines.append(self.static.to_user_text())
        return "\n".join(lines)


def _run_phase_analyzers(ctx: AnalysisContext) -> list[PhaseResult]:
    """Populate ModuleInfo caches in dependency order."""
    phases: list[PhaseResult] = []

    # --- patterns ---
    p_ok, p_n = True, 0
    for m in ctx.module_list():
        if not m.tree:
            continue
        try:
            m.patterns = analyze_module_patterns(m.tree, m.path)  # type: ignore[attr-defined]
            p_n += len(getattr(m.patterns, "functions", []) or [])
        except Exception as e:
            p_ok = False
            m.patterns = None  # type: ignore[attr-defined]
            phases.append(PhaseResult("patterns", False, f"{m.path}: {type(e).__name__}"))
    if p_ok:
        phases.append(PhaseResult("patterns", True, f"functions={p_n}", {"functions": p_n}))

    # --- dataflow (may already be set by build_context) ---
    d_ok, d_n = True, 0
    for m in ctx.module_list():
        if not m.tree:
            continue
        if m.flow is not None:
            d_n += len(getattr(m.flow, "functions", []) or [])
            continue
        try:
            m.flow = analyze_module_flow(m.tree, m.path)
            d_n += len(m.flow.functions)
        except Exception as e:
            d_ok = False
            m.flow = None
            phases.append(PhaseResult("dataflow", False, f"{m.path}: {type(e).__name__}"))
    if d_ok:
        phases.append(PhaseResult("dataflow", True, f"functions={d_n}", {"functions": d_n}))

    # --- contracts ---
    c_ok, c_n = True, 0
    for m in ctx.module_list():
        if not m.tree:
            continue
        try:
            m.contracts = analyze_module_contracts(m.tree, m.path)  # type: ignore[attr-defined]
            c_n += len(getattr(m.contracts, "functions", []) or [])
        except Exception as e:
            c_ok = False
            m.contracts = None  # type: ignore[attr-defined]
            phases.append(PhaseResult("contracts", False, f"{m.path}: {type(e).__name__}"))
    if c_ok:
        phases.append(PhaseResult("contracts", True, f"functions={c_n}", {"functions": c_n}))

    # --- symbolic (most expensive — last) ---
    s_ok, s_n, s_paths = True, 0, 0
    for m in ctx.module_list():
        if not m.tree:
            continue
        try:
            m.symbolic = analyze_module_symbolic(m.tree, m.path)  # type: ignore[attr-defined]
            s_n += len(getattr(m.symbolic, "functions", []) or [])
            s_paths += sum(getattr(fn, "paths_explored", 0) for fn in (m.symbolic.functions or []))
        except Exception as e:
            s_ok = False
            m.symbolic = None  # type: ignore[attr-defined]
            phases.append(PhaseResult("symbolic", False, f"{m.path}: {type(e).__name__}"))
    if s_ok:
        phases.append(PhaseResult(
            "symbolic", True,
            f"functions={s_n} paths={s_paths}",
            {"functions": s_n, "paths": s_paths},
        ))

    # --- conversation / flow graph (project-level) ---
    try:
        flow_rep = analyze_conversation_flow(ctx.root)
        n_err = len(flow_rep.errors)
        phases.append(PhaseResult(
            "conversation_flow",
            flow_rep.ok,
            f"states={len(flow_rep.states)} paths={flow_rep.paths_explored} errors={n_err}",
            dict(flow_rep.coverage),
        ))
        # inject findings into static report later via meta; attach on ctx
        ctx.meta = getattr(ctx, "meta", {}) or {}
        ctx.meta["conversation_flow"] = {
            "ok": flow_rep.ok,
            "findings": [
                {"severity": f.severity, "code": f.code, "message": f.message, "path": f.path}
                for f in flow_rep.findings
            ],
            "coverage": flow_rep.coverage,
        }
        # promote errors into static findings list after run_rules — store for run_pipeline
        ctx.meta["conversation_flow_errors"] = [
            f for f in flow_rep.findings if f.severity == "error"
        ]
    except Exception as e:
        phases.append(PhaseResult("conversation_flow", False, f"{type(e).__name__}: {e}"))

    return phases


def run_pipeline(
    root: str,
    focus_files: list[str] | None = None,
    expected_commands: list[str] | None = None,
    tags: list[str] | None = None,
) -> PipelineReport:
    """
    Full ordered static analysis pipeline.

    1. Build context (parse + symbols + baseline flow)
    2. Run phase analyzers in order (patterns → dataflow → contracts → symbolic)
    3. Run all rules against the enriched context
    """
    ctx = build_context(
        root,
        focus_files=focus_files,
        expected_commands=expected_commands,
    )
    phase_results = _run_phase_analyzers(ctx)
    static = run_rules(ctx, tags=tags)
    # promote conversation_flow errors into static findings
    cf_meta = (getattr(ctx, "meta", None) or {}).get("conversation_flow") or {}
    for item in cf_meta.get("findings") or []:
        if item.get("severity") != "error":
            continue
        static.findings.append(
            StaticFinding(
                severity="error",
                code=item.get("code") or "conversation_flow",
                file=item.get("path") or "conversation_flow",
                message_ar=item.get("message") or "",
                lineno=0,
                rule_id="conversation_flow",
                evidence=item.get("evidence") or "",
            )
        )
    static.errors = sum(1 for f in static.findings if f.severity == "error")
    static.warnings = sum(1 for f in static.findings if f.severity == "warning")
    static.infos = sum(1 for f in static.findings if f.severity == "info")
    static.ok = static.errors == 0
    ok = static.ok and all(p.ok for p in phase_results)
    meta = {
        "phase_order": list(PHASE_ORDER),
        "module_count": len(ctx.modules),
        "rules_run": list(static.rules_run),
    }
    if cf_meta:
        meta["conversation_flow"] = cf_meta
    return PipelineReport(
        ok=ok,
        static=static,
        phases=phase_results,
        meta=meta,
    )


def analyze_unified(
    root: str,
    focus_files: list[str] | None = None,
    tags: list[str] | None = None,
) -> PipelineReport:
    """Alias for run_pipeline — preferred entry for callers."""
    return run_pipeline(root, focus_files=focus_files, tags=tags)
