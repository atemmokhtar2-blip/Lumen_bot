from __future__ import annotations
import re
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta

_TOKEN_RE = re.compile(
    r"""(?:BOT_TOKEN|TELEGRAM_BOT_TOKEN|API_TOKEN|TOKEN)\s*=\s*['\"]([0-9]{6,}:[A-Za-z0-9_-]{20,})['\"]"""
)
_HARDCODED_SECRET = re.compile(
    r"""(?:api_key|secret_key|password)\s*=\s*['\"][^'\"]{8,}['\"]""",
    re.I,
)


class HardcodedTokenRule:
    meta = RuleMeta(
        "hardcoded_token",
        "توكن/أسرار مضمّنة في الكود",
        tags=("security", "telegram"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            for i, line in enumerate(m.source.splitlines(), 1):
                if _TOKEN_RE.search(line):
                    out.append(StaticFinding(
                        severity="error",
                        code="hardcoded_bot_token",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=i,
                        message_ar="توكن بوت مضمّن في الكود — استخدم متغير بيئة",
                    ))
                elif _HARDCODED_SECRET.search(line) and "example" not in line.lower():
                    out.append(StaticFinding(
                        severity="warning",
                        code="hardcoded_secret",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=i,
                        message_ar="قيمة سرية قد تكون مضمّنة في الكود",
                    ))
        return out
