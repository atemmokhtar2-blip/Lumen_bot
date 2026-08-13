from __future__ import annotations
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta

class SyntaxRule:
    meta = RuleMeta("syntax", "أخطاء بناء الجملة", tags=("core", "gate"))

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if m.syntax_error:
                out.append(StaticFinding(
                    severity="error",
                    code="syntax",
                    rule_id=self.meta.id,
                    file=m.path,
                    message_ar=f"SyntaxError: {m.syntax_error}",
                ))
        return out
