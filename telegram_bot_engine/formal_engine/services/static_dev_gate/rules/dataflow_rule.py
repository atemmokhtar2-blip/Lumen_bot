"""Rules powered by Control & Data Flow Analysis on AST."""

from __future__ import annotations

from ..dataflow import analyze_module_flow, ModuleFlow
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta


def _flow_for(m) -> ModuleFlow | None:
    if m.flow is not None:
        return m.flow  # type: ignore[return-value]
    if not m.tree:
        return None
    return analyze_module_flow(m.tree, m.path)


class UseBeforeDefRule:
    meta = RuleMeta(
        "use_before_def",
        "متغير يُستخدم قبل تعيينه (dataflow)",
        tags=("dataflow", "core", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            flow = _flow_for(m)
            if not flow:
                continue
            for fn in flow.functions:
                seen: set[tuple[str, int]] = set()
                for name, ln in fn.use_before_def:
                    key = (name, ln)
                    if key in seen:
                        continue
                    seen.add(key)
                    if name in m.functions or name in m.classes:
                        continue
                    st = m.symbol_table
                    if st is not None and getattr(st, "has_global", lambda n: False)(name):
                        continue
                    if any(
                        imp[0].split(".")[-1] == name or imp[0].split(".")[0] == name
                        for imp in m.imports
                    ):
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
            flow = _flow_for(m)
            if not flow:
                continue
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
        "استدعاءات خطرة مع مدخلات ديناميكية",
        tags=("dataflow", "security", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            flow = _flow_for(m)
            if not flow:
                continue
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


class TaintToSinkRule:
    meta = RuleMeta(
        "taint_to_sink",
        "بيانات مستخدم (message/update) تصل لاستدعاء حساس",
        tags=("dataflow", "security", "telegram", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            flow = _flow_for(m)
            if not flow:
                continue
            for fn in flow.functions:
                for src, sink, ln in fn.tainted_to_sink:
                    # only high-risk sinks
                    risky = any(
                        x in sink
                        for x in ("eval", "exec", "system", "popen", "Popen", "pickle", "compile")
                    )
                    if not risky:
                        continue
                    out.append(
                        StaticFinding(
                            severity="error",
                            code="taint_to_sink",
                            rule_id=self.meta.id,
                            file=m.path,
                            lineno=ln,
                            message_ar=f"تدفق غير آمن: `{src}` → `{sink}` في `{fn.qualname}`",
                            evidence=f"{src}->{sink}",
                        )
                    )
        return out


class AsyncNoAwaitRule:
    meta = RuleMeta(
        "async_no_await",
        "دالة async بدون await (قد تكون خطأ تصميم)",
        tags=("quality", "async"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            flow = _flow_for(m)
            if not flow:
                continue
            for fn in flow.functions:
                if fn.is_async and not fn.has_await:
                    # allow simple reply-only handlers that still should await — flag as warning
                    out.append(
                        StaticFinding(
                            severity="warning",
                            code="async_no_await",
                            rule_id=self.meta.id,
                            file=m.path,
                            lineno=fn.lineno,
                            message_ar=f"دالة async `{fn.qualname}` بدون أي await",
                            evidence=fn.qualname,
                        )
                    )
        return out
