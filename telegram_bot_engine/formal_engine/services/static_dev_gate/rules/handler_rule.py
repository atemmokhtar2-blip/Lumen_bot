from __future__ import annotations
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta

class HandlerConsistencyRule:
    meta = RuleMeta(
        "handler_consistency",
        "تسجيل الأوامر يشير لدوال موجودة",
        tags=("core", "telegram", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        seen: dict[str, str] = {}
        for m in ctx.module_list():
            for cmd, handler, ln, style in m.command_regs:
                key = cmd.lower()
                if key in seen and seen[key] != m.path:
                    out.append(StaticFinding(
                        severity="warning",
                        code="duplicate_command",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=ln,
                        message_ar=f"الأمر /{cmd} مسجّل أيضاً في `{seen[key]}`",
                    ))
                seen[key] = m.path
                if handler and handler not in ctx.all_functions:
                    out.append(StaticFinding(
                        severity="error",
                        code="handler_missing",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=ln,
                        message_ar=(
                            f"CommandHandler(/{cmd}) [{style}] → `{handler}` "
                            "غير معرّفة في المشروع المفحوص"
                        ),
                    ))
        return out


class ExpectedCommandsRule:
    meta = RuleMeta(
        "expected_commands",
        "الأوامر المتوقعة بعد التطوير ظاهرة في الكود",
        tags=("gate", "telegram"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        if not ctx.expected_commands:
            return []
        found: set[str] = set()
        for m in ctx.module_list():
            for cmd, _, _, _ in m.command_regs:
                found.add(cmd.lower())
            # string presence for generated modules
            for cmd in ctx.expected_commands:
                if f'CommandHandler("{cmd}"' in m.source or f"Command('{cmd}')" in m.source:
                    found.add(cmd.lower())
                if f'commands=["{cmd}"]' in m.source or f"commands=['{cmd}']" in m.source:
                    found.add(cmd.lower())
        out: list[StaticFinding] = []
        for cmd in ctx.expected_commands:
            if cmd.lower() not in found:
                out.append(StaticFinding(
                    severity="error",
                    code="expected_command_missing",
                    rule_id=self.meta.id,
                    file="gate",
                    message_ar=f"بعد التعديل: الأمر /{cmd} غير ظاهر في التسجيل",
                ))
        return out
