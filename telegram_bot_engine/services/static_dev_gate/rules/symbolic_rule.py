"""Rules powered by Symbolic Execution (path-sensitive analysis)."""

from __future__ import annotations

from ..models import AnalysisContext, StaticFinding
from ..symbolic import analyze_module_symbolic, SymbolicModuleResult
from .base import RuleMeta


def _sym_for(m) -> SymbolicModuleResult | None:
    cached = getattr(m, "symbolic", None)
    if cached is not None:
        return cached
    if not m.tree:
        return None
    result = analyze_module_symbolic(m.tree, m.path)
    try:
        m.symbolic = result  # cache on ModuleInfo for other rules
    except Exception:
        pass
    return result


class SymbolicDivZeroRule:
    meta = RuleMeta(
        "sym_div_by_zero",
        "قسمة رمزية على صفر محتمل عبر مسار",
        tags=("symbolic", "crash", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            sym = _sym_for(m)
            if not sym:
                continue
            for fn in sym.functions:
                for f in fn.findings:
                    if f.kind != "div_by_zero":
                        continue
                    out.append(StaticFinding(
                        severity=f.severity,
                        code="sym_div_by_zero",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno,
                        message_ar=f"{f.message} في `{fn.qualname}`",
                        evidence=f.path_condition or fn.qualname,
                    ))
        return out


class SymbolicAssertRule:
    meta = RuleMeta(
        "sym_assert_fail",
        "assert قد يفشل أو يفشل حتمًا على مسار رمزي",
        tags=("symbolic", "crash", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            sym = _sym_for(m)
            if not sym:
                continue
            for fn in sym.functions:
                for f in fn.findings:
                    if f.kind != "assert_fail":
                        continue
                    out.append(StaticFinding(
                        severity=f.severity,
                        code="sym_assert_fail",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno,
                        message_ar=f"{f.message} في `{fn.qualname}`",
                        evidence=f.path_condition or fn.qualname,
                    ))
        return out


class SymbolicNoneAccessRule:
    meta = RuleMeta(
        "sym_none_access",
        "وصول لصفة/فهرس على قيمة قد تكون None (مسار رمزي)",
        tags=("symbolic", "nullability", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            sym = _sym_for(m)
            if not sym:
                continue
            for fn in sym.functions:
                for f in fn.findings:
                    if f.kind != "none_access":
                        continue
                    out.append(StaticFinding(
                        severity=f.severity,
                        code="sym_none_access",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno,
                        message_ar=f"{f.message} في `{fn.qualname}`",
                        evidence=f.path_condition or fn.qualname,
                    ))
        return out


class SymbolicAlwaysRaiseRule:
    meta = RuleMeta(
        "sym_always_raise",
        "كل المسارات الرمزية تنتهي بـ raise",
        tags=("symbolic", "crash", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            sym = _sym_for(m)
            if not sym:
                continue
            for fn in sym.functions:
                if not fn.always_raises:
                    continue
                for f in fn.findings:
                    if f.kind != "always_raise":
                        continue
                    out.append(StaticFinding(
                        severity="error",
                        code="sym_always_raise",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno or fn.lineno,
                        message_ar=f.message,
                        evidence=f"paths={fn.paths_explored}",
                    ))
        return out
