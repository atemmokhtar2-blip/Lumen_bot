from __future__ import annotations
import ast
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta


class EmptyExceptRule:
    meta = RuleMeta(
        "empty_except",
        "except فارغ أو يمرّر بصمت",
        tags=("quality",),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if not m.tree:
                continue
            for node in ast.walk(m.tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body = node.body
                if len(body) == 1 and isinstance(body[0], ast.Pass):
                    out.append(StaticFinding(
                        severity="warning",
                        code="empty_except",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=getattr(node, "lineno", 0) or 0,
                        message_ar="except يبتلع الخطأ بـ pass",
                    ))
                elif len(body) == 1 and isinstance(body[0], ast.Expr):
                    # except: ... bare continue style
                    pass
        return out


class BareExceptRule:
    meta = RuleMeta(
        "bare_except",
        "except عريض (ExceptException أو بدون نوع)",
        tags=("quality",),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if not m.tree:
                continue
            for node in ast.walk(m.tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                # bare except:
                if node.type is None:
                    out.append(StaticFinding(
                        severity="warning",
                        code="bare_except",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=getattr(node, "lineno", 0) or 0,
                        message_ar="except: بدون نوع — يفضّل except Exception",
                    ))
        return out
