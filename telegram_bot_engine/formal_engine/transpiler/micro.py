"""
Micro-Transpiler.

Builds Python source Statement by Statement from InferenceResult.
Does not know domain services. Only emits programming logic (Python Syntax)
that expresses the inferred relations and operations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..inference.engine import DecisionPlan, InferenceResult, LoopPlan, SchemaPlan


def _ident(name: str) -> str:
    # ASCII-only identifiers for valid Python syntax
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not re.match(r"[a-zA-Z]", s[0] if s else ""):
        s = "n_" + (s or "x")
    # drop leading underscores after n_ prefix normalization
    if s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _cls(name: str) -> str:
    parts = [p for p in _ident(name).split("_") if p]
    return "".join(p.capitalize() for p in parts) or "Item"


def _py(s: Any) -> str:
    return repr(s)


def _emit_schema_module(schemas: list[SchemaPlan]) -> str:
    lines: list[str] = [
        '"""Schema — unique tables from inference (not generic)."""',
        "from __future__ import annotations",
        "from dataclasses import dataclass, field",
        "from typing import Any",
        "",
    ]
    for sch in schemas:
        cname = _cls(sch.table)
        lines.append("@dataclass")
        lines.append(f"class {cname}:")
        if not sch.columns:
            lines.append("    id: str = \"\"")
        else:
            for col, typ in sch.columns:
                if typ == "int":
                    lines.append(f"    {_ident(col)}: int = 0")
                elif typ == "bool":
                    lines.append(f"    {_ident(col)}: bool = False")
                else:
                    lines.append(f"    {_ident(col)}: str = \"\"")
        lines.append("")
        # store dict helper
        lines.append(f"    def to_dict(self) -> dict[str, Any]:")
        lines.append("        return {")
        for col, _typ in sch.columns:
            lines.append(f"            {_py(_ident(col))}: self.{_ident(col)},")
        lines.append("        }")
        lines.append("")
    if not schemas:
        lines += [
            "@dataclass",
            "class Record:",
            "    id: str = \"\"",
            "    payload: str = \"\"",
            "",
            "    def to_dict(self) -> dict[str, Any]:",
            "        return {\"id\": self.id, \"payload\": self.payload}",
            "",
        ]
    return "\n".join(lines) + "\n"


def _emit_store_module(schemas: list[SchemaPlan]) -> str:
    lines: list[str] = [
        '"""In-memory unique stores derived from schemas."""',
        "from __future__ import annotations",
        "from typing import Any",
        "import uuid",
        "from app.models import *",  # noqa: models module emits schema classes
        "",
    ]
    for sch in schemas:
        cname = _cls(sch.table)
        sname = _ident(sch.table)
        lines.append(f"class {_cls(sch.table)}Store:")
        lines.append("    def __init__(self) -> None:")
        lines.append("        self._rows: dict[str, Any] = {}")
        lines.append("")
        lines.append("    async def create(self, **fields: Any) -> str:")
        lines.append("        oid = str(fields.get(\"id\") or uuid.uuid4())")
        lines.append(f"        obj = {cname}(**{{k: v for k, v in fields.items() if k in {cname}.__dataclass_fields__}})")
        lines.append("        obj.id = oid")
        lines.append("        self._rows[oid] = obj")
        lines.append("        return oid")
        lines.append("")
        lines.append("    async def get(self, oid: str) -> Any:")
        lines.append("        return self._rows.get(str(oid))")
        lines.append("")
        lines.append("    async def list_all(self) -> list[Any]:")
        lines.append("        return list(self._rows.values())")
        lines.append("")
        lines.append("    async def list_by_user(self, user_id: int) -> list[Any]:")
        lines.append("        out = []")
        lines.append("        for r in self._rows.values():")
        lines.append("            if getattr(r, \"user_id\", None) == user_id:")
        lines.append("                out.append(r)")
        lines.append("        return out")
        lines.append("")
    if not schemas:
        lines += [
            "class RecordStore:",
            "    def __init__(self) -> None:",
            "        self._rows: dict[str, Any] = {}",
            "",
            "    async def create(self, **fields: Any) -> str:",
            "        oid = str(fields.get(\"id\") or uuid.uuid4())",
            "        self._rows[oid] = dict(fields, id=oid)",
            "        return oid",
            "",
            "    async def get(self, oid: str) -> Any:",
            "        return self._rows.get(str(oid))",
            "",
            "    async def list_all(self) -> list[Any]:",
            "        return list(self._rows.values())",
            "",
        ]
    return "\n".join(lines) + "\n"


def _emit_logic_module(inf: InferenceResult) -> str:
    """Core logic: loops, decisions, actions — statement by statement."""
    lines: list[str] = [
        '"""Inferred logic — loops, decisions, actions."""',
        "from __future__ import annotations",
        "from typing import Any",
        "",
    ]

    # Decision trees
    for d in inf.decisions:
        fname = _ident(d.name)
        lines.append(f"def {fname}(discriminant: Any) -> str:")
        lines.append(f"    \"\"\"Decision tree: {d.name}.\"\"\"")
        if not d.branches:
            lines.append("    return \"default\"")
        else:
            for i, br in enumerate(d.branches):
                label = str(br.get("label") or f"b{i}")
                target = str(br.get("target") or f"path_{i}")
                kw = "if" if i == 0 else "elif"
                lines.append(f"    {kw} str(discriminant) == {_py(label)} or {_py(label)} in str(discriminant):")
                lines.append(f"        return {_py(target)}")
            lines.append("    return \"default\"")
        lines.append("")

    # Loops
    for lp in inf.loops:
        fname = _ident(lp.name)
        lines.append(f"def {fname}(items: list[Any]) -> list[Any]:")
        lines.append(f"    \"\"\"Loop over {lp.iterable}.\"\"\"")
        lines.append("    result: list[Any] = []")
        lines.append("    for item in list(items or []):")
        lines.append("        result.append(item)")
        lines.append("    return result")
        lines.append("")

    # Actions from relations
    for aname in inf.actions:
        fname = _ident(aname)
        lines.append(f"async def {fname}(store: Any = None, user_id: int = 0, payload: dict | None = None) -> str:")
        lines.append(f"    \"\"\"Action {aname} derived from relation.\"\"\"")
        lines.append("    payload = dict(payload or {})")
        lines.append("    payload.setdefault(\"user_id\", user_id)")
        lines.append("    if store is not None and hasattr(store, \"create\"):")
        lines.append("        oid = await store.create(**payload)")
        lines.append("        return f\"ok:{oid}\"")
        lines.append("    return \"ok\"")
        lines.append("")

    # Compute steps as sequential functions
    for step in inf.compute_steps:
        fname = _ident(step["name"])
        label = step.get("label") or step["name"]
        lines.append(f"def {fname}(context: dict[str, Any]) -> dict[str, Any]:")
        lines.append(f"    \"\"\"{label[:80]}\"\"\"")
        lines.append("    ctx = dict(context or {})")
        lines.append(f"    ctx[{_py('last_step')}] = {_py(step['name'])}")
        lines.append("    return ctx")
        lines.append("")

    if len(lines) <= 4:
        lines += [
            "def noop(context: dict[str, Any] | None = None) -> dict[str, Any]:",
            "    return dict(context or {})",
            "",
        ]
    return "\n".join(lines) + "\n"


def _emit_handlers_module(inf: InferenceResult) -> str:
    """Handlers composed from inferred receives/emits/actions — no domain templates."""
    lines: list[str] = [
        '"""Handlers synthesized from receive/emit operations."""',
        "from __future__ import annotations",
        "from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup",
        "from telegram.ext import ContextTypes",
        "from app import logic",
        "from app.store import *",  # noqa
        "from app.container import get_container",
        "",
        "",
        "async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    if message is None:",
        "        return",
        "    context.user_data.clear()",
        "    # sequential compute steps drive the first prompt if present",
    ]
    if inf.compute_steps:
        first = inf.compute_steps[0]
        lines.append(f"    context.user_data[\"state\"] = {_py(first['name'])}")
        lines.append(f"    await message.reply_text({_py(str(first.get('label') or first['name'])[:200])})")
    else:
        lines.append("    await message.reply_text(\"ready\")")
    lines.append("")
    lines.append("")
    lines.append("async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    await message.reply_text(\"help\")")
    lines.append("")
    lines.append("")
    lines.append("async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    ud = context.user_data")
    lines.append("    state = ud.get(\"state\")")
    lines.append("    text = (message.text or \"\").strip()")
    lines.append("    # photo / document as payload values")
    lines.append("    if message.photo:")
    lines.append("        text = message.photo[-1].file_id")
    lines.append("    elif message.document:")
    lines.append("        text = message.document.file_id")
    lines.append("    if not state:")
    lines.append("        await message.reply_text(\"use /start\")")
    lines.append("        return")
    lines.append("    collected = dict(ud.get(\"collected\") or {})")
    lines.append("    collected[str(state)] = text")
    lines.append("    ud[\"collected\"] = collected")
    # wire decisions
    if inf.decisions:
        d = inf.decisions[0]
        fname = _ident(d.name)
        lines.append(f"    branch = logic.{fname}(text)")
        lines.append("    ud[\"branch\"] = branch")
    # advance compute steps linearly
    if inf.compute_steps:
        names = [s["name"] for s in inf.compute_steps]
        lines.append(f"    _order = {[ _ident(n) for n in names ]!r}")
        lines.append("    try:")
        lines.append("        idx = _order.index(str(state))")
        lines.append("    except ValueError:")
        lines.append("        idx = -1")
        lines.append("    if idx >= 0 and idx + 1 < len(_order):")
        lines.append("        nxt = _order[idx + 1]")
        lines.append("        ud[\"state\"] = nxt")
        # prompt map
        prompt_map = { _ident(s["name"]): str(s.get("label") or s["name"])[:200] for s in inf.compute_steps }
        lines.append(f"        _prompts = {prompt_map!r}")
        lines.append("        await message.reply_text(_prompts.get(nxt, nxt))")
        lines.append("        return")
    lines.append("    ud.pop(\"state\", None)")
    # final action call
    if inf.actions:
        aname = _ident(inf.actions[0])
        lines.append("    container = get_container()")
        lines.append("    store = getattr(container, \"primary_store\", None)")
        lines.append("    _uid = message.from_user.id if message.from_user else 0")
        lines.append(f"    result = await logic.{aname}(store=store, user_id=_uid, payload=collected)")
        lines.append("    await message.reply_text(str(result))")
    else:
        lines.append("    await message.reply_text(str(collected))")
    lines.append("")
    lines.append("")
    lines.append("async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    await query.answer()")
    lines.append("    data = query.data or \"\"")
    lines.append("    context.user_data[\"choice\"] = data")
    if inf.decisions:
        d = inf.decisions[0]
        fname = _ident(d.name)
        lines.append(f"    branch = logic.{fname}(data)")
        lines.append("    context.user_data[\"branch\"] = branch")
        lines.append("    await query.edit_message_text(str(branch))")
    else:
        lines.append("    await query.edit_message_text(data)")
    lines.append("")
    return "\n".join(lines) + "\n"


def _emit_container(inf: InferenceResult) -> str:
    lines = [
        '"""DI container — stores inferred from schemas only."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from app import store as store_mod",
        "",
        "",
        "class Container:",
        "    def __init__(self) -> None:",
    ]
    if inf.schemas:
        first = True
        for sch in inf.schemas:
            sname = _ident(sch.table)
            cstore = _cls(sch.table) + "Store"
            lines.append(f"        self.{sname} = store_mod.{cstore}()")
            if first:
                lines.append(f"        self.primary_store = self.{sname}")
                first = False
    else:
        lines.append("        self.primary_store = store_mod.RecordStore()")
    lines += [
        "",
        "",
        "@lru_cache(maxsize=1)",
        "def get_container() -> Container:",
        "    return Container()",
        "",
    ]
    return "\n".join(lines) + "\n"


def _emit_main(inf: InferenceResult) -> str:
    lines = [
        '"""Entry — wiring only."""',
        "from __future__ import annotations",
        "import logging",
        "import sys",
        "from telegram import Update",
        "from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters",
        "from app.config import get_settings",
        "from app.handlers import start_handler, help_handler, message_handler, callback_handler",
        "",
        "logging.basicConfig(",
        "    format=\"%(asctime)s | %(levelname)-8s | %(name)s | %(message)s\",",
        "    level=logging.INFO,",
        "    stream=sys.stdout,",
        ")",
        "logger = logging.getLogger(\"bot\")",
        "",
        "",
        "def build_application() -> Application:",
        "    settings = get_settings()",
        "    app = Application.builder().token(settings.telegram_bot_token).build()",
        "    app.add_handler(CommandHandler(\"start\", start_handler))",
        "    app.add_handler(CommandHandler(\"help\", help_handler))",
        "    app.add_handler(CallbackQueryHandler(callback_handler))",
        "    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))",
        "    app.add_handler(MessageHandler(filters.PHOTO, message_handler))",
        "    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))",
        "    return app",
        "",
        "",
        "def main() -> None:",
        "    logger.info(\"starting\")",
        "    build_application().run_polling(allowed_updates=Update.ALL_TYPES)",
        "",
        "",
        "if __name__ == \"__main__\":",
        "    main()",
        "",
    ]
    return "\n".join(lines)


def _emit_config() -> str:
    return '''"""Typed config — env only."""
from __future__ import annotations
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    telegram_bot_token: str = Field(..., min_length=20)
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
'''


def _emit_requirements() -> str:
    return "\n".join(
        [
            "python-telegram-bot>=21.0",
            "pydantic>=2.0",
            "pydantic-settings>=2.0",
        ]
    ) + "\n"


def _emit_env() -> str:
    return "TELEGRAM_BOT_TOKEN=\nLOG_LEVEL=INFO\n"


def transpile(inf: InferenceResult, out_dir: str | Path) -> list[str]:
    """
    Micro-transpile InferenceResult → project files.
    Statement-level emission only. Returns list of written paths.
    """
    root = Path(out_dir)
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    def w(rel: str, content: str) -> None:
        path = root / rel if not rel.startswith("app/") else root / rel
        if rel.startswith("app/"):
            path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")
        written.append(str(path))

    w("app/__init__.py", '"""app package"""\n')
    w("app/models.py", _emit_schema_module(inf.schemas))
    w("app/store.py", _emit_store_module(inf.schemas))
    w("app/logic.py", _emit_logic_module(inf))
    w("app/handlers.py", _emit_handlers_module(inf))
    w("app/container.py", _emit_container(inf))
    w("app/config.py", _emit_config())
    w("main.py", _emit_main(inf))
    w("requirements.txt", _emit_requirements())
    w(".env.example", _emit_env())
    return written
