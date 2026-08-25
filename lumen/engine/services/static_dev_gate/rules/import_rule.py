from __future__ import annotations
from ..models import AnalysisContext, StaticFinding
from .base import RuleMeta

_THIRD = {
    "telegram", "aiogram", "telebot", "pyrogram", "telethon",
    "pydantic", "dotenv", "httpx", "aiohttp", "requests",
    "openai", "google", "redis", "sqlalchemy", "asyncpg",
    "fastapi", "uvicorn", "flask", "django", "numpy", "pandas",
    "pytest", "unittest", "typing_extensions",
}

_STDLIB = {
    "os", "sys", "re", "json", "ast", "time", "datetime", "pathlib", "typing",
    "collections", "functools", "itertools", "subprocess", "asyncio", "logging",
    "hashlib", "base64", "uuid", "copy", "math", "random", "string", "io",
    "tempfile", "shutil", "traceback", "dataclasses", "enum", "abc", "contextlib",
    "importlib", "inspect", "warnings", "platform", "signal", "struct", "queue",
}


class LocalImportRule:
    meta = RuleMeta(
        "local_import",
        "الاستيرادات المحلية تشير لملفات موجودة",
        tags=("core", "gate"),
    )

    def check(self, ctx: AnalysisContext) -> list[StaticFinding]:
        out: list[StaticFinding] = []
        for m in ctx.module_list():
            for mod, ln in m.imports:
                top = mod.split(".")[0]
                if top in _STDLIB or top in _THIRD:
                    continue
                if top in ctx.local_module_names:
                    continue
                # only flag likely project modules to reduce noise
                if top.startswith("active_dev") or top in {
                    "handlers", "config", "keyboards", "middlewares",
                    "states", "services", "utils", "db", "models",
                }:
                    out.append(StaticFinding(
                        severity="error",
                        code="missing_local_module",
                        rule_id=self.meta.id,
                        file=m.path,
                        lineno=ln,
                        message_ar=f"استيراد محلي `{mod}` بدون ملف/حزمة مطابقة",
                    ))
        return out
