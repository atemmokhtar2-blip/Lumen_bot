from __future__ import annotations
import re
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta


class TelegramEntryRule:
    meta = RuleMeta(
        "telegram_entry",
        "نقطة تشغيل البوت وتسجيل handlers",
        tags=("telegram", "quality"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        has_run = False
        has_any_handler = False
        entry_files = []
        for m in ctx.module_list():
            if m.path.endswith(("main.py", "bot.py", "app.py")) or m.path in (
                "main.py", "bot.py", "app.py",
            ):
                entry_files.append(m)
            if re.search(r"run_polling|start_polling|infinity_polling|\.run\(", m.source):
                has_run = True
            if m.command_regs or "add_handler" in m.source or "message_handler" in m.source:
                has_any_handler = True

        if entry_files and has_run and not has_any_handler:
            out.append(StaticFinding(
                severity="warning",
                code="run_without_handlers",
                rule_id=self.meta.id,
                file=entry_files[0].path,
                message_ar="تشغيل البوت بدون handlers ظاهرة — قد لا يستجيب لأوامر",
            ))

        # Application without token env pattern
        for m in entry_files:
            if "Application" in m.source or "TeleBot" in m.source or "Bot(" in m.source:
                if not re.search(
                    r"os\.environ|getenv|BOT_TOKEN|TELEGRAM_BOT_TOKEN|settings\.|config\.",
                    m.source,
                ):
                    out.append(StaticFinding(
                        severity="info",
                        code="token_source_unclear",
                        rule_id=self.meta.id,
                        file=m.path,
                        message_ar="مصدر التوكن غير واضح (يُفضّل env/settings)",
                    ))
        return out
