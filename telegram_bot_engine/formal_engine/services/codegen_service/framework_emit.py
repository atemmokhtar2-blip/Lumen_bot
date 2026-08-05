"""
Framework-aware emitters (PTB vs aiogram) + architecture layer scaffolding.

Driven only by ProgramContract.architecture — no domain templates.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...schemas.program_contract import ProgramContract


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if not s or s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _py(s: str) -> str:
    return repr(s)


def normalize_framework(raw: str) -> str:
    r = (raw or "").strip().lower()
    if "aiogram" in r:
        return "aiogram"
    return "python-telegram-bot"


def normalize_layers(layers: list[str] | None) -> list[str]:
    """Canonical package/module names from free-text layer list."""
    out: list[str] = []
    seen: set[str] = set()
    mapping = {
        "handler": "handlers",
        "handlers": "handlers",
        "service": "services",
        "services": "services",
        "repository": "repositories",
        "repositories": "repositories",
        "repo": "repositories",
        "middleware": "middlewares",
        "middlewares": "middlewares",
        "filter": "filters",
        "filters": "filters",
        "model": "models",
        "models": "models",
        "configuration": "config",
        "configurations": "config",
        "config": "config",
        "utility": "utils",
        "utilities": "utils",
        "utils": "utils",
        "domain": "domain",
        "usecase": "usecases",
        "usecases": "usecases",
        "use_cases": "usecases",
        "infrastructure": "infrastructure",
    }
    for raw in layers or []:
        key = re.sub(r"[^a-z0-9_]", "", raw.strip().lower())
        name = mapping.get(key) or mapping.get(key.rstrip("s") + "s") or None
        if not name and key:
            name = key[:32]
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def requirements_for(c: "ProgramContract") -> list[str]:
    fw = normalize_framework(getattr(c.architecture, "framework", "") if c.architecture else "")
    deps: list[str] = []
    if fw == "aiogram":
        deps.append("aiogram>=3.4,<4")
    else:
        deps.append("python-telegram-bot>=21.0,<22")
    deps += [
        "python-dotenv>=1.0.0",
        "pydantic>=2.5,<3",
        "pydantic-settings>=2.1,<3",
    ]
    if c.tech.database == "postgres" or "postgres" in (c.integrations or []):
        deps += ["asyncpg>=0.29.0", "sqlalchemy[asyncio]>=2.0"]
    else:
        deps.append("aiosqlite>=0.20.0")
    if c.tech.async_queue or "redis" in (c.integrations or []):
        deps += ["redis>=5.0", "arq>=0.26.0"]
    if c.tech.payments or "stripe" in (c.integrations or []):
        deps.append("stripe>=8.0")
    return list(dict.fromkeys(deps))


def emit_main_ptb(c: "ProgramContract", commands: list) -> str:
    from .service import _ident as ident, _py as py  # reuse

    extra = [x for x in commands if x.name not in ("start", "help")]
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
        i = ident(cmd.name)
        imports.append(f"from app.handlers.cmd_{i} import {i}_handler")
        regs.append(f'    app.add_handler(CommandHandler("{cmd.name}", {i}_handler))')
    regs += [
        "    app.add_handler(CallbackQueryHandler(callback_handler))",
        "    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))",
    ]
    bot_cmds = "\n".join(
        f"        BotCommand({py(x.name)}, {py((x.description or x.name)[:50])}),"
        for x in commands
    ) or '        BotCommand("start", "start"),'
    log = ident(c.bot_name) or "bot"
    return (
        f'"""\n{c.bot_name} — PTB application (framework from contract).\n"""\n'
        "from __future__ import annotations\n"
        "import logging\n"
        "import sys\n"
        "from telegram import BotCommand, Update\n"
        "from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters\n"
        "from app.config import get_settings\n"
        + "\n".join(imports)
        + "\n\n"
        'logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", '
        "level=logging.INFO, stream=sys.stdout)\n"
        f"logger = logging.getLogger({py(log)})\n\n\n"
        "async def _post_init(app: Application) -> None:\n"
        "    await app.bot.set_my_commands([\n"
        + bot_cmds
        + "\n    ])\n\n\n"
        "def build_application() -> Application:\n"
        "    settings = get_settings()\n"
        "    app = Application.builder().token(settings.telegram_bot_token).post_init(_post_init).build()\n"
        + "\n".join(regs)
        + "\n    return app\n\n\n"
        "def main() -> None:\n"
        f"    logger.info(\"Starting %s\", {py(c.bot_name)})\n"
        "    build_application().run_polling(allowed_updates=Update.ALL_TYPES)\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


def emit_main_aiogram(c: "ProgramContract", commands: list) -> str:
    extra = [x for x in commands if x.name not in ("start", "help")]
    imports = [
        "from app.handlers.start import start_handler, help_handler",
        "from app.handlers.callbacks import callback_handler",
        "from app.handlers.messages import message_handler",
    ]
    regs = [
        '    dp.message.register(start_handler, Command("start"))',
        '    dp.message.register(help_handler, Command("help"))',
    ]
    for cmd in extra:
        i = _ident(cmd.name)
        imports.append(f"from app.handlers.cmd_{i} import {i}_handler")
        regs.append(f'    dp.message.register({i}_handler, Command("{cmd.name}"))')
    regs += [
        "    dp.callback_query.register(callback_handler)",
        "    dp.message.register(message_handler)",
    ]
    bot_cmds = ",\n".join(
        f"        BotCommand(command={_py(x.name)}, description={_py((x.description or x.name)[:50])})"
        for x in commands
    ) or '        BotCommand(command="start", description="start")'
    log = _ident(c.bot_name) or "bot"
    return f'''"""
{c.bot_name} — aiogram 3 application (framework from contract).
"""
from __future__ import annotations
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BotCommand
from app.config import get_settings
{chr(10).join(imports)}

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger({_py(log)})


async def _setup(bot: Bot) -> None:
    await bot.set_my_commands([
{bot_cmds}
    ])


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
{chr(10).join(regs)}
    return dp


async def _run() -> None:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()
    await _setup(bot)
    logger.info("Starting %s", {_py(c.bot_name)})
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
'''


def emit_start_aiogram(c: "ProgramContract", welcome: str, help_txt: str, kb_rows: list[str]) -> str:
    kb = ",\n".join(kb_rows) if kb_rows else '        [InlineKeyboardButton(text="القائمة", callback_data="main_menu")]'
    return f'''"""UI entry — aiogram handlers from contract."""
from __future__ import annotations
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.container import get_container


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
{kb}
    ])


async def start_handler(message: Message) -> None:
    user = message.from_user
    container = get_container()
    if user is not None and hasattr(container, "users"):
        await container.users.ensure_user(
            telegram_id=user.id,
            username=user.username,
            full_name=(user.full_name or user.first_name or ""),
        )
    await message.answer({_py(welcome)}, reply_markup=main_keyboard())


async def help_handler(message: Message) -> None:
    await message.answer({_py(help_txt)}, reply_markup=main_keyboard())
'''


def emit_cmd_aiogram(name: str, description: str, admin_only: bool) -> str:
    fn = f"{_ident(name)}_handler"
    desc = description or name
    lines = [
        f'"""Command /{name} — {desc} (aiogram)."""',
        "from __future__ import annotations",
        "from aiogram.types import Message",
        "from app.container import get_container",
    ]
    if admin_only or name == "admin":
        lines.append("from app.config import get_settings")
    lines += ["", "", f"async def {fn}(message: Message) -> None:"]
    if admin_only or name == "admin":
        lines += [
            "    settings = get_settings()",
            "    user = message.from_user",
            "    if user is None:",
            "        return",
            "    if settings.admin_ids and user.id not in settings.admin_ids:",
            '        await message.answer("هذا الأمر للإدارة فقط.")',
            "        return",
        ]
    lines += [
        "    container = get_container()",
        "    args = (message.text or \"\").split()[1:]",
        "    user = message.from_user",
        "    uid = user.id if user is not None else 0",
        f"    svc = getattr(container, {_py(name)}, None) or getattr(container, {_py(_ident(name))}, None)",
        '    if svc is not None and hasattr(svc, "handle"):',
        "        result = await svc.handle(user_id=uid, args=args)",
        "        await message.answer(result if isinstance(result, str) else str(result))",
        "        return",
        f"    await message.answer({_py('/' + name + ' — ' + desc)})",
        "",
    ]
    return "\n".join(lines) + "\n"


def emit_callbacks_aiogram(c: "ProgramContract") -> str:
    cases = []
    for b in c.buttons or []:
        cases.append(
            f"    if data == {_py(b.callback_id)}:\n"
            f"        await callback.message.edit_text({_py(b.label)})\n"
            f"        return\n"
        )
    body = "\n".join(cases) if cases else "    pass\n"
    return (
        '"""Callbacks — aiogram."""\n'
        "from __future__ import annotations\n"
        "from aiogram.types import CallbackQuery\n\n\n"
        "async def callback_handler(callback: CallbackQuery) -> None:\n"
        "    await callback.answer()\n"
        '    data = callback.data or ""\n'
        + body
        + '    if callback.message:\n'
        '        await callback.message.edit_text(f"Action: {data}")\n'
    )


def emit_messages_aiogram(c: "ProgramContract") -> str:
    if not c.conversation_states:
        return '''"""Text fallback — aiogram."""
from __future__ import annotations
from aiogram.types import Message


async def message_handler(message: Message) -> None:
    if not message.text:
        return
    await message.answer("Use /start or menu buttons.")
'''
    return '''"""Text handler with conversation states — aiogram."""
from __future__ import annotations
from aiogram.types import Message
from app.states import STATE_PROMPTS, UserState

# FSM-lite via bot memory is out of scope; simple reply
async def message_handler(message: Message) -> None:
    if not message.text:
        return
    await message.answer("Use /start or menu buttons.")
'''


def layer_paths_to_create(c: "ProgramContract") -> list[str]:
    """Relative paths under app/ for requested architecture layers."""
    layers = normalize_layers(list(getattr(c.architecture, "layers", None) or []))
    di = bool(getattr(c.architecture, "dependency_injection", False))
    style = (getattr(c.architecture, "style", "") or "").lower()
    if "clean" in style or di or getattr(c.quality, "modular_code", False):
        for must in ("handlers", "services", "repositories", "config", "models"):
            if must not in layers:
                layers.append(must)
    paths: list[str] = []
    for layer in layers:
        if layer in ("handlers", "services", "domain", "usecases", "infrastructure"):
            paths.append(f"app/{layer}/__init__.py")
        elif layer == "repositories":
            paths.append("app/repositories.py")
        elif layer == "middlewares":
            paths.append("app/middlewares.py")
        elif layer == "filters":
            paths.append("app/filters.py")
        elif layer == "utils":
            paths.append("app/utils.py")
        elif layer == "config":
            paths.append("app/config.py")
        elif layer == "models":
            paths.append("app/models.py")
    if di or "clean" in style:
        paths.append("app/container.py")
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
