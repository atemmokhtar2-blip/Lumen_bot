from __future__ import annotations
import re
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta


def _norm(cmd: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (cmd or "").lower())


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
        found_norm: set[str] = set()
        for m in ctx.module_list():
            for cmd, _, _, _ in m.command_regs:
                found.add(cmd.lower())
                found_norm.add(_norm(cmd))
            src = m.source or ""
            for cmd in ctx.expected_commands:
                c = cmd.lower()
                patterns = (
                    f'CommandHandler("{c}"',
                    f"CommandHandler('{c}'",
                    f'Command("{c}")',
                    f"Command('{c}')",
                    f'commands=["{c}"]',
                    f"commands=['{c}']",
                    f'BotCommand("{c}"',
                    f"BotCommand('{c}'",
                    f'BotCommand(command="{c}"',
                    f"BotCommand(command='{c}'",
                )
                if any(p in src for p in patterns):
                    found.add(c)
                    found_norm.add(_norm(c))
        out: list[StaticFinding] = []
        for cmd in ctx.expected_commands:
            c = cmd.lower()
            if c in found or _norm(c) in found_norm:
                continue
            out.append(StaticFinding(
                severity="error",
                code="expected_command_missing",
                rule_id=self.meta.id,
                file="gate",
                message_ar=f"بعد التعديل: الأمر /{cmd} غير ظاهر في التسجيل",
            ))
        return out
