"""Rules powered by AST Pattern Matching (structural / semantic)."""

from __future__ import annotations

from ..models import AnalysisContext, StaticFinding
from ..patterns import analyze_module_patterns, PatternModuleResult
from .base import RuleMeta


def _pat_for(m) -> PatternModuleResult | None:
    cached = getattr(m, "patterns", None)
    if cached is not None:
        return cached
    if not m.tree:
        return None
    result = analyze_module_patterns(m.tree, m.path)
    try:
        m.patterns = result
    except Exception:
        pass
    return result


class HighComplexityRule:
    meta = RuleMeta(
        "high_complexity",
        "تعقيد دائري مرتفع (Cyclomatic Complexity)",
        tags=("patterns", "clean-code", "quality"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            pat = _pat_for(m)
            if not pat:
                continue
            for fn in pat.functions:
                for f in fn.findings:
                    if f.kind != "high_complexity":
                        continue
                    out.append(StaticFinding(
                        severity=f.severity,
                        code="high_complexity",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno,
                        message_ar=f.message,
                        evidence=f.evidence,
                    ))
        return out


class DuplicatedCodeRule:
    meta = RuleMeta(
        "duplicated_code",
        "تكرار هيكلي يخالف مبدأ DRY",
        tags=("patterns", "clean-code", "dry"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        seen: set[tuple[str, int]] = set()
        for m in ctx.module_list():
            pat = _pat_for(m)
            if not pat:
                continue
            for f in pat.findings:
                if f.kind != "duplicated_code":
                    continue
                key = (f.qualname, f.lineno)
                if key in seen:
                    continue
                seen.add(key)
                out.append(StaticFinding(
                    severity=f.severity,
                    code="duplicated_code",
                    rule_id=self.meta.id,
                    file=m.path,
                    lineno=f.lineno,
                    message_ar=f.message,
                    evidence=f.evidence,
                ))
        return out


class MissingExceptRule:
    meta = RuleMeta(
        "missing_except",
        "استدعاء خطر بدون معالجة استثناء",
        tags=("patterns", "clean-code", "exceptions"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            pat = _pat_for(m)
            if not pat:
                continue
            for fn in pat.functions:
                for f in fn.findings:
                    if f.kind != "missing_except":
                        continue
                    out.append(StaticFinding(
                        severity=f.severity,
                        code="missing_except",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=f.lineno,
                        message_ar=f.message,
                        evidence=f.evidence,
                    ))
        return out
