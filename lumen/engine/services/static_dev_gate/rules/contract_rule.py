"""Rules powered by Design-by-Contract + static type checking."""

from __future__ import annotations

from ..models import AnalysisContext, StaticFinding
from ..contracts import analyze_module_contracts, ContractModuleResult
from .base import RuleMeta


def _con_for(m) -> ContractModuleResult | None:
    cached = getattr(m, "contracts", None)
    if cached is not None:
        return cached
    if not m.tree:
        return None
    result = analyze_module_contracts(m.tree, m.path)
    try:
        m.contracts = result
    except Exception:
        pass
    return result


class MissingAnnotationRule:
    meta = RuleMeta(
        "missing_annotation",
        "عقد ناقص: معاملات أو إرجاع بدون نوع (API عام)",
        tags=("contracts", "types", "quality"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            con = _con_for(m)
            if not con:
                continue
            for f in con.findings:
                if f.kind != "missing_annotation":
                    continue
                out.append(StaticFinding(
                    severity=f.severity,
                    code="missing_annotation",
                    rule_id=self.meta.id,
                    file=m.path,
                    lineno=f.lineno,
                    message_ar=f.message,
                    evidence=f.evidence,
                ))
        return out


class TypeMismatchRule:
    meta = RuleMeta(
        "type_mismatch",
        "تعارض نوع مع العقد المعلن (annotation)",
        tags=("contracts", "types", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            con = _con_for(m)
            if not con:
                continue
            for f in con.findings:
                if f.kind != "type_mismatch":
                    continue
                out.append(StaticFinding(
                    severity=f.severity,
                    code="type_mismatch",
                    rule_id=self.meta.id,
                    file=m.path,
                    lineno=f.lineno,
                    message_ar=f.message,
                    evidence=f.evidence,
                ))
        return out


class BadBinOpRule:
    meta = RuleMeta(
        "bad_binop",
        "عملية على أنواع غير متوافقة",
        tags=("contracts", "types", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            con = _con_for(m)
            if not con:
                continue
            for f in con.findings:
                if f.kind != "bad_binop":
                    continue
                out.append(StaticFinding(
                    severity=f.severity,
                    code="bad_binop",
                    rule_id=self.meta.id,
                    file=m.path,
                    lineno=f.lineno,
                    message_ar=f.message,
                    evidence=f.evidence,
                ))
        return out


class UnsatPreconditionRule:
    meta = RuleMeta(
        "unsat_precondition",
        "شرط مسبق مستحيل التحقق",
        tags=("contracts", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            con = _con_for(m)
            if not con:
                continue
            for f in con.findings:
                if f.kind != "unsat_precondition":
                    continue
                out.append(StaticFinding(
                    severity=f.severity,
                    code="unsat_precondition",
                    rule_id=self.meta.id,
                    file=m.path,
                    lineno=f.lineno,
                    message_ar=f.message,
                    evidence=f.evidence,
                ))
        return out
