"""
Dynamic code assembly from FormalBotSpec only.

NO domain templates. NO fixed shop/ticket handlers.
Every file is derived from what understanding extracted:
commands, buttons, handlers, data_models, services, flags.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..schemas.formal_spec import FormalBotSpec


def _safe_ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if not s or s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _py_str(s: str) -> str:
    return repr(s)


def render_requirements(spec: FormalBotSpec) -> str:
    deps = [
        "python-telegram-bot>=21.0,<22",
        "python-dotenv>=1.0.0",
        "pydantic>=2.5,<3",
        "pydantic-settings>=2.1,<3",
    ]
    integ = set(spec.integrations or [])
    if spec.database.value == "postgres" or "postgres" in integ:
        deps += ["asyncpg>=0.29.0", "sqlalchemy[asyncio]>=2.0"]
    else:
        deps.append("aiosqlite>=0.20.0")
    if spec.requires_async_queue or "redis" in integ:
        deps += ["redis>=5.0", "arq>=0.26.0"]
    if spec.requires_payments or "stripe" in integ:
        deps.append("stripe>=8.0")
    return "\n".join(dict.fromkeys(deps)) + "\n"


def render_env_example(spec: FormalBotSpec) -> str:
    lines = [
        "TELEGRAM_BOT_TOKEN=",
        "ALLOWED_USER_IDS=",
        "ADMIN_USER_IDS=",
        f"BOT_NAME={spec.bot_name}",
        "LOG_LEVEL=INFO",
        "",
    ]
    if spec.database.value == "postgres":
        lines += ["DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/botdb", ""]
    if spec.requires_async_queue:
        lines += ["REDIS_URL=redis://localhost:6379/0", ""]
    if spec.requires_payments:
        lines += ["STRIPE_SECRET_KEY=", ""]
    return "\n".join(lines)


def render_config(spec: FormalBotSpec) -> str:
    return f'''"""Typed configuration — from environment only."""
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
    bot_name: str = {_py_str(spec.bot_name)}
    log_level: str = "INFO"
    database_url: str | None = None
    redis_url: str | None = None

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def _as_str(cls, v: object) -> str:
        return "" if v is None else str(v)

    def _parse_ids(self, raw: str) -> Set[int]:
        if not raw.strip():
            return set()
        return {{int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}}

    @property
    def allowed_ids(self) -> Set[int]:
        return self._parse_ids(self.allowed_user_ids)

    @property
    def admin_ids(self) -> Set[int]:
        return self._parse_ids(self.admin_user_ids)

@lru_cache
def get_settings() -> Settings:
    return Settings()
'''


def render_models(spec: FormalBotSpec) -> str:
    lines = [
        '"""Domain models — assembled only from understood data_models."""',
        "from __future__ import annotations",
        "from typing import Any",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "class StrictModel(BaseModel):",
        '    model_config = ConfigDict(frozen=True, extra="forbid")',
        "",
    ]
    if not spec.data_models:
        lines += [
            "class User(StrictModel):",
            "    id: int = 0",
            "    telegram_id: int = 0",
            '    full_name: str = ""',
            "",
        ]
    for m in spec.data_models:
        lines.append(f"class {m.name}(StrictModel):")
        typed = list(getattr(m, "typed_fields", None) or [])
        if typed:
            for f in typed:
                th = f.type_hint or "str"
                if th == "int":
                    lines.append(f"    {f.name}: int = 0")
                elif th == "bool":
                    lines.append(f"    {f.name}: bool = False")
                elif "list" in th:
                    lines.append(f"    {f.name}: list[Any] = Field(default_factory=list)")
                elif "dict" in th:
                    lines.append(f"    {f.name}: dict[str, Any] = Field(default_factory=dict)")
                elif "None" in th:
                    lines.append(f"    {f.name}: {th} = None")
                else:
                    lines.append(f'    {f.name}: str = ""')
        else:
            for name in m.fields or ["id"]:
                lines.append(f'    {name}: str = ""')
        lines.append("")
    return "\n".join(lines) + "\n"


def render_start_handler(spec: FormalBotSpec) -> str:
    rows = []
    for b in (spec.ui.main_buttons or [])[:10]:
        rows.append(
            f'        [InlineKeyboardButton({_py_str(b.text)}, callback_data={_py_str(b.callback_data)})]'
        )
    if not rows:
        rows = ['        [InlineKeyboardButton("Start", callback_data="main_menu")]']
    buttons_code = ",\n".join(rows)
    welcome = spec.ui.welcome_message or f"Welcome to {spec.bot_name}"
    cmd_help = "\n".join(
        f"/{c.command} — {c.description}" for c in (spec.ui.commands or [])
    ) or "/start"
    return f'''"""Entry handlers — buttons & commands come from FormalBotSpec.ui only."""
from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


def main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
{buttons_code}
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        {_py_str(welcome)},
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        {_py_str("*Commands:*\\n" + cmd_help)},
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(),
    )
'''


def render_command_handler(command: str, description: str, admin_only: bool, spec: FormalBotSpec) -> str:
    """One handler module per understood command — no domain hardcoding."""
    fn = f"{_safe_ident(command)}_handler"
    guard = ""
    if admin_only or command == "admin":
        guard = '''
    settings = get_settings()
    user = update.effective_user
    if user is None:
        return
    if settings.admin_ids and user.id not in settings.admin_ids:
        await message.reply_text("⛔ Admin only.")
        return
'''
        imports = "from app.config import get_settings\n"
    else:
        imports = ""

    return f'''"""Handler for /{command} — description from user spec: {description[:80]}."""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes
{imports}

async def {fn}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
{guard}
    await message.reply_text(
        {_py_str(f"/{command}: {description}")}
    )
'''


def render_callbacks(spec: FormalBotSpec) -> str:
    """Route every understood button callback_data — no fixed domain routes."""
    cases = []
    for b in spec.ui.main_buttons or []:
        cases.append(
            f"    if data == {_py_str(b.callback_data)}:\n"
            f"        await query.edit_message_text({_py_str('Selected: ' + b.text)})\n"
            f"        return\n"
        )
    body = "\n".join(cases) if cases else "    pass\n"
    return f'''"""Callback router — built from FormalBotSpec.ui.main_buttons only."""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
{body}
    await query.edit_message_text(f"Action: {{data}}")
'''


def render_messages(spec: FormalBotSpec) -> str:
    return '''"""Text message fallback — state can be extended from understood flows."""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    await message.reply_text("Use /start or the menu buttons.")
'''


def render_service(name: str, spec: FormalBotSpec) -> str:
    cls = "".join(p.capitalize() for p in _safe_ident(name).split("_")) + "Service"
    return f'''"""Service `{name}` — scaffold from understood services list."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class {cls}:
    def run(self, *args, **kwargs):
        logger.info("%s.run", { _py_str(name) })
        return {{"ok": True, "service": {_py_str(name)}}}
'''


def render_main(spec: FormalBotSpec) -> str:
    cmds = [c for c in (spec.ui.commands or []) if c.command not in ("start", "help")]
    imports = [
        "from app.handlers.start import start_handler, help_handler",
        "from app.handlers.callbacks import callback_handler",
        "from app.handlers.messages import message_handler",
    ]
    regs = [
        '    app.add_handler(CommandHandler("start", start_handler))',
        '    app.add_handler(CommandHandler("help", help_handler))',
    ]
    for c in cmds:
        ident = _safe_ident(c.command)
        imports.append(f"from app.handlers.cmd_{ident} import {ident}_handler")
        regs.append(f'    app.add_handler(CommandHandler("{c.command}", {ident}_handler))')
    regs.append("    app.add_handler(CallbackQueryHandler(callback_handler))")
    regs.append("    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))")
    logger_name = _safe_ident(spec.bot_name) or "bot"
    return f'''"""
{spec.bot_name} — assembled from FormalBotSpec (no domain templates).
"""
from __future__ import annotations
import logging
import sys
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from app.config import get_settings
{chr(10).join(imports)}

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger({_py_str(logger_name)})


def build_application() -> Application:
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()
{chr(10).join(regs)}
    return app


def main() -> None:
    logger.info("Starting %s", {_py_str(spec.bot_name)})
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
'''


def render_readme(spec: FormalBotSpec) -> str:
    cmds = ", ".join(f"/{c.command}" for c in spec.ui.commands) or "/start"
    btns = ", ".join(b.text for b in spec.ui.main_buttons) or "—"
    return f"""# {spec.bot_name}

Assembled by Formal Engine from your description (no fixed domain template).

- Type (detected): `{spec.bot_type.value}`
- Commands: {cmds}
- Buttons: {btns}
- Models: {', '.join(m.name for m in spec.data_models) or '—'}
- Services: {', '.join(spec.services) or '—'}

```bash
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```
"""


def render_pyproject(spec: FormalBotSpec) -> str:
    name = re.sub(r"[^a-z0-9]+", "-", spec.bot_name.lower()).strip("-") or "telegram-bot"
    return f'''[project]
name = "{name}"
version = "1.0.0"
requires-python = ">=3.11"
'''
