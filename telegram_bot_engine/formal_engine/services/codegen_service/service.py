"""
Codegen Service — ProgramContract → project files.

BLIND to raw user text. Only consumes ProgramContract.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...schemas.program_contract import FieldType, ProgramContract
from ...generation.post_verify import verify_generated_project


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if not s or s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _py(s: str) -> str:
    return repr(s)


def _type_hint(ft: FieldType) -> str:
    return {
        FieldType.STR: "str",
        FieldType.INT: "int",
        FieldType.BOOL: "bool",
        FieldType.FLOAT: "float",
        FieldType.LIST: "list",
        FieldType.DICT: "dict",
        FieldType.OPTIONAL_STR: "str | None",
        FieldType.OPTIONAL_INT: "int | None",
    }.get(ft, "str")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")


def _requirements(c: ProgramContract) -> str:
    from .framework_emit import requirements_for
    return "\n".join(requirements_for(c)) + "\n"


def _env(c: ProgramContract) -> str:
    lines = [
        "TELEGRAM_BOT_TOKEN=",
        "ALLOWED_USER_IDS=",
        "ADMIN_USER_IDS=",
        f"BOT_NAME={c.bot_name}",
        "LOG_LEVEL=INFO",
        "",
    ]
    if c.tech.database == "postgres":
        lines += ["DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/botdb", ""]
    if c.tech.async_queue:
        lines += ["REDIS_URL=redis://localhost:6379/0", ""]
    if c.tech.payments:
        lines += ["STRIPE_SECRET_KEY=", ""]
    return "\n".join(lines)


def _config(c: ProgramContract) -> str:
    return f'''"""Typed config — env only."""
from __future__ import annotations
from functools import lru_cache
from typing import Set
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    telegram_bot_token: str = Field(..., min_length=20)
    allowed_user_ids: str = ""
    admin_user_ids: str = ""
    bot_name: str = {_py(c.bot_name)}
    log_level: str = "INFO"
    database_url: str | None = None
    redis_url: str | None = None

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def _s(cls, v: object) -> str:
        return "" if v is None else str(v)

    def _ids(self, raw: str) -> Set[int]:
        if not raw.strip():
            return set()
        return {{int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}}

    @property
    def allowed_ids(self) -> Set[int]:
        return self._ids(self.allowed_user_ids)

    @property
    def admin_ids(self) -> Set[int]:
        return self._ids(self.admin_user_ids)

@lru_cache
def get_settings() -> Settings:
    return Settings()
'''


def _models(c: ProgramContract) -> str:
    lines = [
        '"""Entities from ProgramContract.entities only."""',
        "from __future__ import annotations",
        "from typing import Any",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "class StrictModel(BaseModel):",
        '    model_config = ConfigDict(frozen=True, extra="forbid")',
        "",
    ]
    entities = list(c.entities) or []
    if not entities:
        lines += ["class User(StrictModel):", "    id: int = 0", '    full_name: str = ""', ""]
    for e in entities:
        lines.append(f"class {e.name}(StrictModel):")
        if not e.fields:
            lines.append('    id: str = ""')
        for f in e.fields:
            th = _type_hint(f.field_type)
            if th == "int":
                lines.append(f"    {f.name}: int = 0")
            elif th == "bool":
                lines.append(f"    {f.name}: bool = False")
            elif th == "list":
                lines.append(f"    {f.name}: list[Any] = Field(default_factory=list)")
            elif th == "dict":
                lines.append(f"    {f.name}: dict[str, Any] = Field(default_factory=dict)")
            elif "None" in th:
                lines.append(f"    {f.name}: {th} = None")
            else:
                lines.append(f'    {f.name}: str = ""')
        lines.append("")
    return "\n".join(lines) + "\n"


def _start(c: ProgramContract, commands=None, buttons=None) -> str:
    from .enrichment import effective_buttons, effective_commands, help_text, welcome_text

    cmds = commands if commands is not None else effective_commands(c)
    btns = buttons if buttons is not None else effective_buttons(c)
    rows = []
    for b in btns:
        rows.append(
            f"        [InlineKeyboardButton({_py(b.label)}, callback_data={_py(b.callback_id)})]"
        )
    if not rows:
        rows = ['        [InlineKeyboardButton("القائمة", callback_data="main_menu")]']
    kb = ",\n".join(rows)
    welcome = welcome_text(c)
    help_txt = help_text(cmds)
    return f'''"""UI entry — commands/buttons derived from ProgramContract."""
from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from app.container import get_container


def main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
{kb}
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    user = update.effective_user
    container = get_container()
    if user is not None and hasattr(container, "users"):
        await container.users.ensure_user(
            telegram_id=user.id,
            username=user.username,
            full_name=(user.full_name or user.first_name or ""),
        )
    await message.reply_text({_py(welcome)}, reply_markup=main_keyboard())


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text({_py(help_txt)}, reply_markup=main_keyboard())
'''


def _callbacks(c: ProgramContract) -> str:
    first_state = c.conversation_states[0].name if c.conversation_states else None
    cases: list[str] = []
    for b in c.buttons:
        if first_state:
            cases.append(
                "    if data == %s:\n"
                "        context.user_data[\"state\"] = %s\n"
                "        await query.edit_message_text(%s)\n"
                "        return\n"
                % (_py(b.callback_id), _py(first_state), _py(b.label + " — send details as text"))
            )
        else:
            cases.append(
                "    if data == %s:\n"
                "        await query.edit_message_text(%s)\n"
                "        return\n"
                % (_py(b.callback_id), _py(b.label))
            )
    body = "\n".join(cases) if cases else "    pass\n"
    return (
        '"""Callbacks from ProgramContract.buttons."""\n'
        "from __future__ import annotations\n"
        "from telegram import Update\n"
        "from telegram.ext import ContextTypes\n\n\n"
        "async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
        "    query = update.callback_query\n"
        "    if query is None:\n"
        "        return\n"
        "    await query.answer()\n"
        "    data = query.data or \"\"\n"
        + body
        + "    await query.edit_message_text(f\"Action: {data}\")\n"
    )



def _cmd_handler(
    name: str,
    description: str,
    admin_only: bool,
    entity_names: list[str] | None = None,
) -> str:
    """Command handler — generic dispatch to container service if present."""
    fn = f"{_ident(name)}_handler"
    desc = description or name
    lines: list[str] = [
        f'"""Command /{name} — {desc}."""',
        "from __future__ import annotations",
        "",
        "from telegram import Update",
        "from telegram.ext import ContextTypes",
        "from app.container import get_container",
    ]
    if admin_only or name == "admin":
        lines.append("from app.config import get_settings")
    lines.extend(["", "", f"async def {fn}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:"])
    lines.extend(
        [
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
        ]
    )
    if admin_only or name == "admin":
        lines.extend(
            [
                "    settings = get_settings()",
                "    user = update.effective_user",
                "    if user is None:",
                "        return",
                "    if settings.admin_ids and user.id not in settings.admin_ids:",
                '        await message.reply_text("هذا الأمر للإدارة فقط.")',
                "        return",
            ]
        )
    lines.extend(
        [
            "    container = get_container()",
            "    args = list(context.args or [])",
            "    user = update.effective_user",
            "    uid = user.id if user is not None else 0",
            f"    svc = getattr(container, {_py(name)}, None)",
            "    if svc is None:",
            f"        svc = getattr(container, {_py(_ident(name))}, None)",
            '    if svc is not None and hasattr(svc, "handle"):',
            "        result = await svc.handle(user_id=uid, args=args)",
            "        text = result if isinstance(result, str) else str(result)",
            "        await message.reply_text(text)",
            "        return",
            f'    await message.reply_text({_py("/" + name + " — " + desc)})',
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _service(name: str, responsibility: str = "") -> str:
    from .behavior import emit_rich_service
    return emit_rich_service(name, responsibility)



def _repository_module(c: ProgramContract) -> str:
    """Repositories: Postgres when tech.database is postgres, else in-memory."""
    entities = list(c.entities or [])
    use_pg = (getattr(c.tech, "database", "") or "").lower() in (
        "postgres", "postgresql", "pg",
    )
    L: list[str] = []

    def a(s: str = "") -> None:
        L.append(s)

    a('"""Repositories — entity stores (contract-driven)."""')
    a("from __future__ import annotations")
    a("import os")
    a("import uuid")
    a("from typing import Any")
    a("")
    a("")
    if use_pg:
        a('_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()')
        a("_PG_POOL = None")
        a("")
        a("")
        a("async def _pg_pool():")
        a("    global _PG_POOL")
        a("    if _PG_POOL is not None:")
        a("        return _PG_POOL")
        a("    if not _DATABASE_URL:")
        a("        return None")
        a("    try:")
        a("        import asyncpg")
        a('        dsn = _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")')
        a('        dsn = dsn.replace("postgres+asyncpg://", "postgresql://")')
        a("        _PG_POOL = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)")
        a("        return _PG_POOL")
        a("    except Exception:")
        a("        return None")
        a("")
        a("")
        a("class InMemoryStore:")
        a("    def __init__(self) -> None:")
        a("        self._data: dict[str, list[Any]] = {}")
        a("")
        a("    def bucket(self, name: str) -> list[Any]:")
        a('        return self._data.setdefault(name, [])')
        a("")
        a("")
        a("_STORE = InMemoryStore()")
        a("")
        a("")
        a("class GenericRepository:")
        a('    """Postgres when DATABASE_URL works; otherwise in-memory fallback."""')
        a("    def __init__(self, bucket: str) -> None:")
        a("        self._bucket = bucket")
        a('        self._table = "t_" + "".join(ch if ch.isalnum() else "_" for ch in bucket.lower())[:40]')
        a("")
        a("    async def _ensure_table(self, pool) -> None:")
        a("        await pool.execute(")
        a('            f"CREATE TABLE IF NOT EXISTS {self._table} ("')
        a('            "id TEXT PRIMARY KEY, user_id BIGINT, payload JSONB NOT NULL DEFAULT \'{}\'::jsonb)"')
        a("        )")
        a("")
        a("    async def list_all(self) -> list[Any]:")
        a("        pool = await _pg_pool()")
        a("        if pool is None:")
        a("            return list(_STORE.bucket(self._bucket))")
        a("        await self._ensure_table(pool)")
        a('        q = "SELECT id, user_id, payload FROM " + self._table + " ORDER BY id DESC LIMIT 200"')
        a("        rows = await pool.fetch(q)")
        a("        out = []")
        a("        for r in rows:")
        a("            d = dict(r['payload'] or {})")
        a("            d['id'] = r['id']")
        a("            if r['user_id'] is not None:")
        a("                d['user_id'] = r['user_id']")
        a("            out.append(d)")
        a("        return out")
        a("")
        a("    async def list_by_user(self, user_id: int) -> list[Any]:")
        a("        pool = await _pg_pool()")
        a("        if pool is None:")
        a("            out = []")
        a("            for x in _STORE.bucket(self._bucket):")
        a("                uid = x.get('user_id') if isinstance(x, dict) else getattr(x, 'user_id', None)")
        a("                if uid == user_id:")
        a("                    out.append(x)")
        a("            return out")
        a("        await self._ensure_table(pool)")
        a('        q = "SELECT id, user_id, payload FROM " + self._table + " WHERE user_id=$1 ORDER BY id DESC LIMIT 200"')
        a("        rows = await pool.fetch(q, user_id)")
        a("        out = []")
        a("        for r in rows:")
        a("            d = dict(r['payload'] or {})")
        a("            d['id'] = r['id']")
        a("            d['user_id'] = r['user_id']")
        a("            out.append(d)")
        a("        return out")
        a("")
        a("    async def get(self, oid: str) -> Any | None:")
        a("        pool = await _pg_pool()")
        a("        if pool is None:")
        a("            for x in _STORE.bucket(self._bucket):")
        a("                xid = x.get('id') if isinstance(x, dict) else getattr(x, 'id', '')")
        a("                if str(xid) == str(oid):")
        a("                    return x")
        a("            return None")
        a("        await self._ensure_table(pool)")
        a('        q = "SELECT id, user_id, payload FROM " + self._table + " WHERE id=$1"')
        a("        r = await pool.fetchrow(q, str(oid))")
        a("        if r is None:")
        a("            return None")
        a("        d = dict(r['payload'] or {})")
        a("        d['id'] = r['id']")
        a("        if r['user_id'] is not None:")
        a("            d['user_id'] = r['user_id']")
        a("        return d")
        a("")
        a("    async def create(self, **kwargs: Any) -> str:")
        a("        oid = str(kwargs.get('id') or uuid.uuid4().hex[:12])")
        a("        row = dict(kwargs)")
        a("        row['id'] = oid")
        a("        uid = row.get('user_id')")
        a("        uid_val = 0")
        a("        try:")
        a("            if uid is not None:")
        a("                uid_val = int(uid)")
        a("        except (TypeError, ValueError):")
        a("            uid_val = 0")
        a("        pool = await _pg_pool()")
        a("        if pool is None:")
        a("            _STORE.bucket(self._bucket).append(row)")
        a("            return oid")
        a("        await self._ensure_table(pool)")
        a("        import json")
        a("        payload_json = json.dumps(row, ensure_ascii=False)")
        a("        sql = (")
        a('            "INSERT INTO " + self._table + " (id, user_id, payload) VALUES ($1, $2, $3::jsonb) "')
        a('            "ON CONFLICT (id) DO UPDATE SET user_id=EXCLUDED.user_id, payload=EXCLUDED.payload"')
        a("        )")
        a("        await pool.execute(sql, oid, uid_val, payload_json)")
        a("        return oid")
        a("")
        a("    async def count(self) -> int:")
        a("        return len(await self.list_all())")
        a("")
        a("    async def ensure(self, telegram_id: int, username: str | None, full_name: str) -> None:")
        a("        existing = await self.get_by_telegram(telegram_id)")
        a("        if existing is not None:")
        a("            return")
        a("        await self.create(telegram_id=telegram_id, username=username, full_name=full_name, user_id=telegram_id)")
        a("")
        a("    async def get_by_telegram(self, telegram_id: int) -> Any | None:")
        a("        for x in await self.list_all():")
        a("            tid = x.get('telegram_id') if isinstance(x, dict) else getattr(x, 'telegram_id', None)")
        a("            if tid == telegram_id:")
        a("                return x")
        a("        return None")
        a("")
        a("    async def search(self, q: str) -> list[Any]:")
        a("        ql = q.lower()")
        a("        return [x for x in await self.list_all() if ql in str(x).lower()]")
        a("")
    else:
        a("class InMemoryStore:")
        a("    def __init__(self) -> None:")
        a("        self._data: dict[str, list[Any]] = {}")
        a("")
        a("    def bucket(self, name: str) -> list[Any]:")
        a('        return self._data.setdefault(name, [])')
        a("")
        a("")
        a("_STORE = InMemoryStore()")
        a("")
        a("")
        a("class GenericRepository:")
        a("    def __init__(self, bucket: str) -> None:")
        a("        self._bucket = bucket")
        a("")
        a("    async def list_all(self) -> list[Any]:")
        a("        return list(_STORE.bucket(self._bucket))")
        a("")
        a("    async def list_by_user(self, user_id: int) -> list[Any]:")
        a("        out = []")
        a("        for x in _STORE.bucket(self._bucket):")
        a("            uid = x.get('user_id') if isinstance(x, dict) else getattr(x, 'user_id', None)")
        a("            if uid == user_id:")
        a("                out.append(x)")
        a("        return out")
        a("")
        a("    async def get(self, oid: str) -> Any | None:")
        a("        for x in _STORE.bucket(self._bucket):")
        a("            xid = x.get('id') if isinstance(x, dict) else getattr(x, 'id', '')")
        a("            if str(xid) == str(oid):")
        a("                return x")
        a("        return None")
        a("")
        a("    async def create(self, **kwargs: Any) -> str:")
        a("        oid = str(kwargs.get('id') or uuid.uuid4().hex[:12])")
        a("        row = dict(kwargs)")
        a("        row['id'] = oid")
        a("        _STORE.bucket(self._bucket).append(row)")
        a("        return oid")
        a("")
        a("    async def count(self) -> int:")
        a("        return len(_STORE.bucket(self._bucket))")
        a("")
        a("    async def ensure(self, telegram_id: int, username: str | None, full_name: str) -> None:")
        a("        for x in _STORE.bucket(self._bucket):")
        a("            tid = x.get('telegram_id') if isinstance(x, dict) else getattr(x, 'telegram_id', None)")
        a("            if tid == telegram_id:")
        a("                return")
        a('        _STORE.bucket(self._bucket).append({"telegram_id": telegram_id, "username": username, "full_name": full_name})')
        a("")
        a("    async def get_by_telegram(self, telegram_id: int) -> Any | None:")
        a("        for x in _STORE.bucket(self._bucket):")
        a("            tid = x.get('telegram_id') if isinstance(x, dict) else getattr(x, 'telegram_id', None)")
        a("            if tid == telegram_id:")
        a("                return x")
        a("        return None")
        a("")
        a("    async def search(self, q: str) -> list[Any]:")
        a("        ql = q.lower()")
        a("        return [x for x in _STORE.bucket(self._bucket) if ql in str(x).lower()]")
        a("")

    for e in entities:
        snake = _ident(e.name)
        a(f"def make_{snake}_repo() -> GenericRepository:")
        a(f"    return GenericRepository({_py(e.name.lower())})")
        a("")
    if not entities:
        a("def make_default_repo() -> GenericRepository:")
        a('    return GenericRepository("default")')
        a("")
    return "\n".join(L) + "\n"


def _container_module(c: ProgramContract, services: list) -> str:
    """DI container — wire services to matching entity repos when names align."""
    entity_snakes = {_ident(e.name) for e in (c.entities or [])}
    L: list[str] = []
    def a(s: str = "") -> None:
        L.append(s)
    a('"""Dependency injection container — structural wiring."""')
    a("from __future__ import annotations")
    a("from functools import lru_cache")
    a("from app import repositories as repos")
    a("")
    for s in services:
        ident = _ident(s.name)
        cls = "".join(p.capitalize() for p in ident.split("_")) + "Service"
        a(f"from app.services.{ident} import {cls}")
    a("")
    a("")
    a("class Container:")
    a("    def __init__(self) -> None:")
    if not services:
        a("        pass")
    for s in services:
        ident = _ident(s.name)
        cls = "".join(p.capitalize() for p in ident.split("_")) + "Service"
        match = None
        if ident in entity_snakes:
            match = ident
        else:
            stem = ident.rstrip("s")
            if stem in entity_snakes:
                match = stem
        if match:
            a(f"        self.{ident} = {cls}(repo=repos.make_{match}_repo())")
        else:
            a(f"        self.{ident} = {cls}()")
    if "user" in entity_snakes:
        if any(_ident(s.name) == "user" for s in services):
            a("        self.users = self.user")
        else:
            a("        from app.services.user import UserService")
            a("        self.users = UserService(repo=repos.make_user_repo())")
    # structural command→service aliases (name overlap only)
    from .behavior import resolve_service_for_command
    svc_names = [_ident(s.name) for s in services]
    ent_names = [e.name for e in (c.entities or [])]
    from .behavior import primary_entity_snake
    primary = primary_entity_snake(c)
    for cmd in c.commands or []:
        if cmd.name in ("start", "help"):
            continue
        ident = _ident(cmd.name)
        if ident in svc_names:
            continue
        bound = resolve_service_for_command(cmd.name, svc_names, ent_names)
        if not bound and primary and primary in svc_names:
            bound = primary
        if bound and bound != ident:
            a(f"        self.{ident} = self.{bound}")
    a("")
    a("")
    a("@lru_cache")
    a("def get_container() -> Container:")
    a("    return Container()")
    a("")
    return "\n".join(L) + "\n"


def _middleware_module() -> str:
    return '''"""Middlewares — logging / access hooks."""
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def log_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        logger.info("update user=<anonymous>")
        return
    logger.info("update user=%s", user.id)
'''


def _filters_module() -> str:
    return '''"""Custom filters placeholder — extend per contract."""
from __future__ import annotations
from telegram.ext import filters

# Re-export common filters for handlers
TEXT = filters.TEXT
COMMAND = filters.COMMAND
'''


def _utils_module() -> str:
    return '''"""Utilities."""
from __future__ import annotations


def clamp_text(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
'''


def _main(c: ProgramContract, commands=None) -> str:
    from .enrichment import effective_commands

    cmds = commands if commands is not None else effective_commands(c)
    extra = [x for x in cmds if x.name not in ("start", "help")]
    imports = [
        "from app.handlers.start import start_handler, help_handler",
        "from app.handlers.callbacks import callback_handler",
        "from app.handlers.messages import message_handler",
    ]
    regs = [
        '    app.add_handler(CommandHandler("start", start_handler))',
        '    app.add_handler(CommandHandler("help", help_handler))',
    ]
    for cmd in extra:
        ident = _ident(cmd.name)
        imports.append(f"from app.handlers.cmd_{ident} import {ident}_handler")
        regs.append(f'    app.add_handler(CommandHandler("{cmd.name}", {ident}_handler))')
    regs += [
        "    app.add_handler(CallbackQueryHandler(callback_handler))",
        "    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))",
    ]
    # Real media handlers when contract requires file/photo handling (no stubs)
    if getattr(c.tech, "file_handling", False) or "file_handling" in (c.feature_tags or []):
        regs.append(
            "    app.add_handler(MessageHandler(filters.PHOTO, message_handler))"
        )
        regs.append(
            "    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))"
        )
    bot_cmds_lines = []
    for x in cmds:
        bot_cmds_lines.append(
            f"        BotCommand({_py(x.name)}, {_py((x.description or x.name)[:50])}),"
        )
    bot_cmds_block = "\n".join(bot_cmds_lines) if bot_cmds_lines else '        BotCommand("start", "start"),'
    log = _ident(c.bot_name) or "bot"
    return (
        f'"""\n{c.bot_name} — assembled from ProgramContract (enriched tags/entities).\n"""\n'
        "from __future__ import annotations\n"
        "import logging\n"
        "import sys\n"
        "from telegram import BotCommand, Update\n"
        "from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters\n"
        "from app.config import get_settings\n"
        + "\n".join(imports) + "\n\n"
        "logging.basicConfig(format=\"%(asctime)s | %(levelname)-8s | %(name)s | %(message)s\", level=logging.INFO, stream=sys.stdout)\n"
        f"logger = logging.getLogger({_py(log)})\n\n\n"
        "async def _post_init(app: Application) -> None:\n"
        "    await app.bot.set_my_commands([\n"
        + bot_cmds_block + "\n"
        "    ])\n\n\n"
        "def build_application() -> Application:\n"
        "    settings = get_settings()\n"
        "    app = Application.builder().token(settings.telegram_bot_token).post_init(_post_init).build()\n"
        + "\n".join(regs) + "\n"
        "    return app\n\n\n"
        "def main() -> None:\n"
        f"    logger.info(\"Starting %s\", {_py(c.bot_name)})\n"
        "    build_application().run_polling(allowed_updates=Update.ALL_TYPES)\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    )



def _readme(c: ProgramContract) -> str:
    return f"""# {c.bot_name}

Generated via **ProgramContract** pipeline (Understanding → Codegen).

- kind: `{c.bot_kind.value}`
- commands: {', '.join('/'+x.name for x in c.commands)}
- buttons: {', '.join(b.label for b in c.buttons) or '—'}
- entities: {', '.join(e.name for e in c.entities) or '—'}

```bash
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```
"""



def _states_module(c: ProgramContract) -> str:
    lines = [
        '"""Conversation states from ProgramContract.conversation_states."""',
        "from __future__ import annotations",
        "from enum import Enum",
        "",
        "class UserState(str, Enum):",
        '    IDLE = "idle"',
    ]
    for st in c.conversation_states or []:
        key = st.name.upper().replace("-", "_")
        # safe enum name
        import re
        key = re.sub(r"[^A-Z0-9_]", "_", key)[:40]
        if not key or key[0].isdigit():
            key = "S_" + key
        lines.append(f'    {key} = "{st.name}"')
    lines.append("")
    lines.append("STATE_PROMPTS: dict[str, str] = {")
    for st in c.conversation_states or []:
        lines.append(f'    "{st.name}": {repr(st.prompt)},')
    lines.append("}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _messages(c: ProgramContract) -> str:
    if not c.conversation_states:
        return '''"""Text fallback."""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    await message.reply_text("Use /start or menu buttons.")
'''
    # Build next map
    next_map = {st.name: st.next_state for st in c.conversation_states}
    prompts = {st.name: st.prompt for st in c.conversation_states}
    return (
        '''"""Text handler — conversation_states from ProgramContract."""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
from app.states import STATE_PROMPTS, UserState

NEXT_STATE = ''' + repr(next_map) + '''
PROMPTS = ''' + repr(prompts) + '''


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    text = message.text.strip()
    ud = context.user_data
    state = ud.get("state", UserState.IDLE.value)
    if state and state != UserState.IDLE.value:
        ud.setdefault("collected", {})
        ud["collected"][state] = text
        nxt = NEXT_STATE.get(state)
        if nxt:
            ud["state"] = nxt
            await message.reply_text(PROMPTS.get(nxt) or f"Next: {nxt}")
        else:
            ud["state"] = UserState.IDLE.value
            await message.reply_text("Done. Saved: " + ", ".join(ud["collected"].keys()))
        return
    await message.reply_text("Use /start or menu buttons.")
'''
    )


class CodegenService:
    """Microservice: ProgramContract → files. Blind to raw NL; uses full contract."""

    def run(self, contract: ProgramContract, output_dir: str | Path) -> tuple[Path, dict]:
        from .enrichment import (
            effective_buttons,
            effective_commands,
            effective_services,
        )

        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        app = root / "app"
        handlers = app / "handlers"
        services_dir = app / "services"

        cmds = effective_commands(contract)
        btns = effective_buttons(contract)
        svcs = effective_services(contract)
        # structural: ensure a service module exists for each entity name
        from ...schemas.program_contract import ServiceUnit
        have = {_ident(s.name) for s in svcs}
        extra = []
        for e in contract.entities or []:
            snake = _ident(e.name)
            if snake and snake not in have:
                extra.append(ServiceUnit(name=snake, responsibility=e.name))
                have.add(snake)
        if extra:
            svcs = list(svcs) + extra

        _write(root / "requirements.txt", _requirements(contract))
        _write(root / ".env.example", _env(contract))
        _write(root / "README.md", _readme(contract))
        _write(root / "program_contract.json", contract.model_dump_json(indent=2))
        _write(
            root / "pyproject.toml",
            f'[project]\nname = "{_ident(contract.bot_name)}"\nversion = "{contract.version}"\nrequires-python = ">=3.11"\n',
        )
        _write(app / "__init__.py", '"""app"""\n')
        _write(handlers / "__init__.py", '"""handlers"""\n')
        _write(services_dir / "__init__.py", '"""services"""\n')
        _write(app / "config.py", _config(contract))
        _write(app / "models.py", _models(contract))
        _write(app / "repositories.py", _repository_module(contract))
        _write(app / "container.py", _container_module(contract, svcs))
        _write(app / "middlewares.py", _middleware_module())
        _write(app / "filters.py", _filters_module())
        _write(app / "utils.py", _utils_module())
        from .framework_emit import (
            emit_main_aiogram,
            emit_main_ptb,
            emit_start_aiogram,
            emit_cmd_aiogram,
            emit_callbacks_aiogram,
            emit_messages_aiogram,
            normalize_framework,
            layer_paths_to_create,
        )
        from .enrichment import welcome_text, help_text

        fw = normalize_framework(
            getattr(contract.architecture, "framework", "") if contract.architecture else ""
        )
        from .behavior import (
            resolve_service_for_command,
            emit_cmd_aiogram as emit_cmd_aio_beh,
            emit_messages_aiogram as emit_msg_aio_beh,
            emit_callbacks_aiogram as emit_cb_aio_beh,
            emit_messages_ptb,
        )
        svc_names = [_ident(s.name) for s in svcs]
        ent_names = [e.name for e in (contract.entities or [])]

        if fw == "aiogram":
            _write(app / "main.py", emit_main_aiogram(contract, cmds))
            rows = []
            for b in btns:
                rows.append(
                    f"        [InlineKeyboardButton(text={_py(b.label)}, callback_data={_py(b.callback_id)})]"
                )
            if not rows:
                rows = ['        [InlineKeyboardButton(text="القائمة", callback_data="main_menu")]']
            _write(
                handlers / "start.py",
                emit_start_aiogram(contract, welcome_text(contract), help_text(cmds), rows),
            )
            _write(handlers / "callbacks.py", emit_cb_aio_beh(contract))
            _write(handlers / "messages.py", emit_msg_aio_beh(contract))
            for cmd in cmds:
                if cmd.name in ("start", "help"):
                    continue
                ident = _ident(cmd.name)
                bound = resolve_service_for_command(cmd.name, svc_names, ent_names)
                _write(
                    handlers / f"cmd_{ident}.py",
                    emit_cmd_aio_beh(cmd.name, cmd.description, cmd.admin_only, bound),
                )
        else:
            _write(app / "main.py", emit_main_ptb(contract, cmds))
            _write(handlers / "start.py", _start(contract, commands=cmds, buttons=btns))
            _write(handlers / "callbacks.py", _callbacks(contract))
            _write(handlers / "messages.py", emit_messages_ptb(contract))
            entity_names = [e.name for e in contract.entities]
            for cmd in cmds:
                if cmd.name in ("start", "help"):
                    continue
                ident = _ident(cmd.name)
                _write(
                    handlers / f"cmd_{ident}.py",
                    _cmd_handler(cmd.name, cmd.description, cmd.admin_only, entity_names),
                )

        if contract.conversation_states:
            _write(app / "states.py", _states_module(contract))

        for rel in layer_paths_to_create(contract):
            path = root / rel
            if path.exists():
                continue
            if rel.endswith("__init__.py"):
                _write(path, '"""Architecture layer package."""' + chr(10))


        for svc in svcs:
            _write(
                services_dir / f"{_ident(svc.name)}.py",
                _service(svc.name, svc.responsibility),
            )

        verify = verify_generated_project(root)
        return root, verify


def generate_from_contract(contract: ProgramContract, output_dir: str | Path) -> tuple[Path, dict]:
    return CodegenService().run(contract, output_dir)
