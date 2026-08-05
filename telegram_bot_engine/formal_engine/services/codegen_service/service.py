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
    deps = [
        "python-telegram-bot>=21.0,<22",
        "python-dotenv>=1.0.0",
        "pydantic>=2.5,<3",
        "pydantic-settings>=2.1,<3",
    ]
    if c.tech.database == "postgres" or "postgres" in c.integrations:
        deps += ["asyncpg>=0.29.0", "sqlalchemy[asyncio]>=2.0"]
    else:
        deps.append("aiosqlite>=0.20.0")
    if c.tech.async_queue or "redis" in c.integrations:
        deps += ["redis>=5.0", "arq>=0.26.0"]
    if c.tech.payments or "stripe" in c.integrations:
        deps.append("stripe>=8.0")
    return "\n".join(dict.fromkeys(deps)) + "\n"


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
    """Command handler — wires to container services when available."""
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
    # service dispatch by command name
    service_map = {
        "orders": ("orders", "list_orders"),
        "order": ("orders", "get_order"),
        "neworder": ("orders", "create_order_stub"),
        "products": ("catalog", "list_products"),
        "catalog": ("catalog", "list_products"),
        "track": ("orders", "track"),
        "delivery": ("orders", "track"),
        "notifications": ("notifications", "list_for_user"),
        "profile": ("users", "get_profile"),
        "search": ("catalog", "search"),
        "stats": ("orders", "stats"),
        "analytics": ("orders", "stats"),
        "admin": ("orders", "stats"),
        "files": ("storage", "list_files"),
        "customers": ("users", "list_users"),
        "docs": ("storage", "list_files"),
        "rate": ("orders", "list_orders"),
        "group": ("users", "list_users"),
    }
    svc_pair = service_map.get(name)
    lines.append("    container = get_container()")
    lines.append("    args = list(context.args or [])")
    lines.append("    user = update.effective_user")
    lines.append("    uid = user.id if user is not None else 0")
    if svc_pair:
        svc, method = svc_pair
        lines.extend(
            [
                f"    svc = getattr(container, {_py(svc)}, None)",
                f"    if svc is not None and hasattr(svc, {_py(method)}):",
                f"        result = await svc.{method}(user_id=uid, args=args)",
                "        text = result if isinstance(result, str) else str(result)",
                "        await message.reply_text(text)",
                "        return",
            ]
        )
    lines.extend(
        [
            f'    await message.reply_text({_py("/" + name + " — " + desc)})',
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _service(name: str, responsibility: str = "") -> str:
    cls = "".join(p.capitalize() for p in _ident(name).split("_")) + "Service"
    ident = _ident(name)
    # entity-aware methods
    methods = [
        "    async def run(self, *args, **kwargs):",
        f'        return {{"ok": True, "service": {_py(name)}}}',
        "",
    ]
    if ident in ("orders", "core"):
        methods = [
            "    async def list_orders(self, user_id: int = 0, args: list | None = None) -> str:",
            "        rows = await self._repo.list_by_user(user_id) if self._repo else []",
            '        if not rows:',
            '            return "لا توجد طلبات حالياً."',
            '        return "الطلبات:\\n" + "\\n".join(str(r) for r in rows[:20])',
            "",
            "    async def get_order(self, user_id: int = 0, args: list | None = None) -> str:",
            '        oid = (args or [""])[0]',
            "        if not oid:",
            '            return "استخدم: /order <id>"',
            "        row = await self._repo.get(oid) if self._repo else None",
            "        if row is None:",
            '            return "الطلب غير موجود."',
            "        return str(row)",
            "",
            "    async def create_order_stub(self, user_id: int = 0, args: list | None = None) -> str:",
            "        if self._repo is None:",
            '            return "خدمة الطلبات غير مهيأة."',
            "        oid = await self._repo.create(user_id=user_id, items=list(args or []))",
            '        return f"تم إنشاء الطلب: {oid}"',
            "",
            "    async def track(self, user_id: int = 0, args: list | None = None) -> str:",
            '        oid = (args or [""])[0]',
            "        if not oid or self._repo is None:",
            '            return "أدخل: /track <order_id>"',
            "        row = await self._repo.get(oid)",
            "        if row is None:",
            '            return "الطلب غير موجود."',
            '        status = getattr(row, "status", "unknown")',
            '        return f"حالة الطلب {oid}: {status}"',
            "",
            "    async def stats(self, user_id: int = 0, args: list | None = None) -> str:",
            "        n = await self._repo.count() if self._repo else 0",
            '        return f"إجمالي السجلات: {n}"',
            "",
        ]
    elif ident in ("catalog",):
        methods = [
            "    async def list_products(self, user_id: int = 0, args: list | None = None) -> str:",
            "        rows = await self._repo.list_all() if self._repo else []",
            '        if not rows:',
            '            return "لا منتجات في الكتالوج."',
            '        return "المنتجات:\\n" + "\\n".join(str(r) for r in rows[:20])',
            "",
            "    async def search(self, user_id: int = 0, args: list | None = None) -> str:",
            '        q = " ".join(args or []).strip()',
            "        if not q:",
            '            return "استخدم: /search <كلمة>"',
            "        rows = await self._repo.search(q) if self._repo else []",
            '        return "نتائج:\\n" + "\\n".join(str(r) for r in rows[:20]) if rows else "لا نتائج."',
            "",
        ]
    elif ident in ("users",):
        methods = [
            "    async def ensure_user(self, telegram_id: int, username: str | None = None, full_name: str = \"\") -> None:",
            "        if self._repo is not None:",
            "            await self._repo.ensure(telegram_id, username, full_name)",
            "",
            "    async def get_profile(self, user_id: int = 0, args: list | None = None) -> str:",
            "        if self._repo is None:",
            '            return "الملف غير موجود — اضغط /start."',
            "        row = await self._repo.get_by_telegram(user_id)",
            "        if row is None:",
            '            return "الملف غير موجود — اضغط /start."',
            "        return str(row)",
            "",
            "    async def list_users(self, user_id: int = 0, args: list | None = None) -> str:",
            "        rows = await self._repo.list_all() if self._repo else []",
            '        return "المستخدمون:\\n" + "\\n".join(str(r) for r in rows[:30]) if rows else "لا مستخدمين."',
            "",
        ]
    elif ident in ("notifications",):
        methods = [
            "    async def list_for_user(self, user_id: int = 0, args: list | None = None) -> str:",
            "        rows = await self._repo.list_by_user(user_id) if self._repo else []",
            '        return "الإشعارات:\\n" + "\\n".join(str(r) for r in rows[:20]) if rows else "لا إشعارات."',
            "",
        ]
    elif ident in ("storage",):
        methods = [
            "    async def list_files(self, user_id: int = 0, args: list | None = None) -> str:",
            '        return "لا ملفات مرفوعة بعد."',
            "",
        ]

    return f'''"""Service {name} — {responsibility or name}."""
from __future__ import annotations
from typing import Any


class {cls}:
    def __init__(self, repo: Any = None) -> None:
        self._repo = repo

{"".join(line + chr(10) for line in methods)}'''


def _repository_module(c: ProgramContract) -> str:
    """In-memory repositories derived from entities — swap for SQL later."""
    entity_names = [e.name for e in (c.entities or [])]
    has_order = any("order" in n.lower() for n in entity_names)
    has_product = any("product" in n.lower() for n in entity_names)
    has_user = any("user" in n.lower() for n in entity_names)
    has_notif = any("notification" in n.lower() for n in entity_names)

    lines = [
        '"""Repositories — contract entities. In-memory default; DATABASE_URL ready."""',
        "from __future__ import annotations",
        "import uuid",
        "from typing import Any",
        "from app import models",
        "",
        "",
        "class InMemoryStore:",
        "    def __init__(self) -> None:",
        "        self._data: dict[str, list[Any]] = {}",
        "",
        "    def bucket(self, name: str) -> list[Any]:",
        '        return self._data.setdefault(name, [])',
        "",
        "",
        "_STORE = InMemoryStore()",
        "",
    ]
    if has_order or True:
        lines += [
            "class OrderRepository:",
            "    async def list_by_user(self, user_id: int) -> list[Any]:",
            '        return [x for x in _STORE.bucket("orders") if getattr(x, "user_id", None) == user_id]',
            "",
            "    async def get(self, oid: str) -> Any | None:",
            '        for x in _STORE.bucket("orders"):',
            '            if getattr(x, "id", None) == oid:',
            "                return x",
            "        return None",
            "",
            "    async def create(self, user_id: int, items: list | None = None) -> str:",
            "        oid = uuid.uuid4().hex[:12]",
            "        obj = models.Order(",
            "            id=oid, user_id=user_id, items=list(items or []),",
            '            total=0, status="pending", created_at="",',
            "        ) if hasattr(models, 'Order') else {\"id\": oid, \"user_id\": user_id, \"status\": \"pending\"}",
            '        _STORE.bucket("orders").append(obj)',
            "        return oid",
            "",
            "    async def count(self) -> int:",
            '        return len(_STORE.bucket("orders"))',
            "",
            "",
        ]
    if has_product or True:
        lines += [
            "class ProductRepository:",
            "    async def list_all(self) -> list[Any]:",
            '        return list(_STORE.bucket("products"))',
            "",
            "    async def search(self, q: str) -> list[Any]:",
            "        ql = q.lower()",
            '        return [x for x in _STORE.bucket("products") if ql in str(x).lower()]',
            "",
            "",
        ]
    if has_user or True:
        lines += [
            "class UserRepository:",
            "    async def ensure(self, telegram_id: int, username: str | None, full_name: str) -> None:",
            '        for x in _STORE.bucket("users"):',
            '            if getattr(x, "telegram_id", None) == telegram_id:',
            "                return",
            "        if hasattr(models, 'User'):",
            "            obj = models.User(",
            "                id=telegram_id, telegram_id=telegram_id,",
            "                username=username, full_name=full_name or '',",
            '                language="ar", is_admin=False, created_at="",',
            "            )",
            "        else:",
            '            obj = {"telegram_id": telegram_id, "full_name": full_name}',
            '        _STORE.bucket("users").append(obj)',
            "",
            "    async def get_by_telegram(self, telegram_id: int) -> Any | None:",
            '        for x in _STORE.bucket("users"):',
            '            if getattr(x, "telegram_id", None) == telegram_id:',
            "                return x",
            "        return None",
            "",
            "    async def list_all(self) -> list[Any]:",
            '        return list(_STORE.bucket("users"))',
            "",
            "",
        ]
    if has_notif:
        lines += [
            "class NotificationRepository:",
            "    async def list_by_user(self, user_id: int) -> list[Any]:",
            '        return [x for x in _STORE.bucket("notifications") if getattr(x, "user_id", None) == user_id]',
            "",
            "",
        ]
    return "\n".join(lines) + "\n"


def _container_module(c: ProgramContract, services: list) -> str:
    """Simple DI container wiring services ↔ repositories."""
    svc_names = [_ident(s.name) for s in services]
    lines = [
        '"""Dependency injection container — wiring from ProgramContract."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from app import repositories as repos",
        "",
    ]
    for s in services:
        ident = _ident(s.name)
        cls = "".join(p.capitalize() for p in ident.split("_")) + "Service"
        lines.append(f"from app.services.{ident} import {cls}")
    lines += ["", "", "class Container:", "    def __init__(self) -> None:"]
    # repos
    lines.append("        self._orders_repo = repos.OrderRepository()")
    lines.append("        self._products_repo = repos.ProductRepository()")
    lines.append("        self._users_repo = repos.UserRepository()")
    if any("notification" in e.name.lower() for e in (c.entities or [])):
        lines.append("        self._notif_repo = repos.NotificationRepository()")
    for s in services:
        ident = _ident(s.name)
        cls = "".join(p.capitalize() for p in ident.split("_")) + "Service"
        if ident in ("orders", "core"):
            lines.append(f"        self.{ident} = {cls}(repo=self._orders_repo)")
        elif ident == "catalog":
            lines.append(f"        self.{ident} = {cls}(repo=self._products_repo)")
        elif ident == "users":
            lines.append(f"        self.{ident} = {cls}(repo=self._users_repo)")
        elif ident == "notifications":
            lines.append(f"        self.{ident} = {cls}(repo=getattr(self, '_notif_repo', None))")
        else:
            lines.append(f"        self.{ident} = {cls}()")
    # aliases for handlers
    if "orders" not in svc_names:
        lines.append("        from app.services.orders import OrdersService")
        # may not exist - only if we always add orders service in enrichment
        pass
    lines += [
        "",
        "",
        "@lru_cache",
        "def get_container() -> Container:",
        "    return Container()",
        "",
    ]
    return "\n".join(lines) + "\n"


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
        _write(app / "main.py", _main(contract, commands=cmds))
        _write(handlers / "start.py", _start(contract, commands=cmds, buttons=btns))
        _write(handlers / "callbacks.py", _callbacks(contract))
        _write(handlers / "messages.py", _messages(contract))
        if contract.conversation_states:
            _write(app / "states.py", _states_module(contract))

        entity_names = [e.name for e in contract.entities]
        for cmd in cmds:
            if cmd.name in ("start", "help"):
                continue
            ident = _ident(cmd.name)
            _write(
                handlers / f"cmd_{ident}.py",
                _cmd_handler(cmd.name, cmd.description, cmd.admin_only, entity_names),
            )

        for svc in svcs:
            _write(
                services_dir / f"{_ident(svc.name)}.py",
                _service(svc.name, svc.responsibility),
            )

        verify = verify_generated_project(root)
        return root, verify


def generate_from_contract(contract: ProgramContract, output_dir: str | Path) -> tuple[Path, dict]:
    return CodegenService().run(contract, output_dir)
