"""Rules powered by Control & Data Flow Analysis on AST."""

from __future__ import annotations

from ..dataflow import analyze_module_flow
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta


class UseBeforeDefRule:
    meta = RuleMeta(
        "use_before_def",
        "متغير يُستخدم قبل تعيينه (dataflow)",
        tags=("dataflow", "core", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if not m.tree:
                continue
            flow = analyze_module_flow(m.tree, m.path)
            for fn in flow.functions:
                seen: set[tuple[str, int]] = set()
                for name, ln in fn.use_before_def:
                    key = (name, ln)
                    if key in seen:
                        continue
                    seen.add(key)
                    # skip common false positives from outer scopes / imports
                    if name in m.functions or name in m.classes:
                        continue
                    if any(imp[0].split(".")[-1] == name or imp[0].split(".")[0] == name for imp in m.imports):
                        continue
                    out.append(
                        StaticFinding(
                            severity="error",
                            code="use_before_def",
                            rule_id=self.meta.id,
                            file=m.path,
                            lineno=ln,
                            message_ar=f"`{name}` يُستخدم قبل التعيين في `{fn.qualname}`",
                            evidence=fn.qualname,
                        )
                    )
        return out


class UnusedLocalRule:
    meta = RuleMeta(
        "unused_local",
        "متغير محلي مُعيَّن وغير مستخدم",
        tags=("dataflow", "quality"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if not m.tree:
                continue
            flow = analyze_module_flow(m.tree, m.path)
            for fn in flow.functions:
                for name in sorted(fn.unused_locals):
                    out.append(
                        StaticFinding(
                            severity="info",
                            code="unused_local",
                            rule_id=self.meta.id,
                            file=m.path,
                            lineno=fn.lineno,
                            message_ar=f"متغير محلي غير مستخدم `{name}` في `{fn.qualname}`",
                            evidence=fn.qualname,
                        )
                    )
        return out


class DangerousSinkRule:
    meta = RuleMeta(
        "dangerous_sink",
        "استدعاءات خطرة مع مدخلات ديناميكية (eval/exec/system…)",
        tags=("dataflow", "security", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            if not m.tree:
                continue
            flow = analyze_module_flow(m.tree, m.path)
            for fn in flow.functions:
                for call, ln, detail in fn.dangerous_sinks:
                    out.append(
                        StaticFinding(
                            severity="error",
                            code="dangerous_sink",
                            rule_id=self.meta.id,
                            file=m.path,
                            lineno=ln,
                            message_ar=f"استدعاء خطر `{call}` ({detail}) في `{fn.qualname}`",
                            evidence=detail,
                        )
                    )
        return out
