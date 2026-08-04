"""
Blueprint-driven code assembly for materialize.

NO domain templates (no hard-coded ban/mute/company bots).

Code is derived only from:
- Blueprint.commands / Blueprint.handlers (composer output)
- analysis_report features (names + descriptions)
- class_generation reports when they provide source_code

If understanding produced commands X,Y,Z — we emit handlers for X,Y,Z
from those specs, not from a fixed catalogue of bot types.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


def _safe_ident(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", (name or "").strip().lower())
    if not s:
        s = "handler"
    if s[0].isdigit():
        s = "cmd_" + s
    return s


def extract_commands_from_context(context: Any) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []
    seen = set()

    bp = None
    if context is not None:
        # Prefer pipeline Blueprint (CommandSpec list from composer)
        bp = getattr(context, "blueprint", None)
        if bp is None and hasattr(context, "get"):
            bp = context.get("project_blueprint")

    if bp is not None:
        for cmd in getattr(bp, "commands", []) or []:
            name = str(getattr(cmd, "name", "") or "").lstrip("/").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            commands.append({
                "name": name,
                "description": str(getattr(cmd, "description", "") or ""),
                "admin_only": bool(getattr(cmd, "admin_only", False)),
                "group_only": bool(getattr(cmd, "group_only", False)),
                "response_type": str(getattr(cmd, "response_type", "text") or "text"),
            })

    report = context.get("analysis_report") if context and hasattr(context, "get") else None
    if report is not None and not commands:
        for f in getattr(report, "features", []) or []:
            name = str(getattr(f, "name", "") or "").strip().lower()
            if not name or name in seen:
                continue
            if name in {
                "message_handler", "config_loader", "logger", "bot_application",
                "database", "middleware",
            }:
                continue
            seen.add(name)
            desc = str(
                getattr(f, "description", None)
                or getattr(f, "display_name", None)
                or name
            )
            commands.append({
                "name": name.replace(" ", "_")[:32],
                "description": desc,
                "admin_only": False,
                "group_only": False,
                "response_type": "text",
            })

    if "start" not in seen:
        commands.insert(0, {
            "name": "start",
            "description": "Start the bot.",
            "admin_only": False,
            "group_only": False,
            "response_type": "text",
        })
        seen.add("start")
    if "help" not in seen:
        commands.append({
            "name": "help",
            "description": "Show available commands.",
            "admin_only": False,
            "group_only": False,
            "response_type": "text",
        })

    return commands


def extract_handlers_from_context(context: Any) -> List[Dict[str, Any]]:
    handlers: List[Dict[str, Any]] = []
    bp = None
    if context is not None:
        bp = getattr(context, "blueprint", None)
        if bp is None and hasattr(context, "get"):
            bp = context.get("project_blueprint")
    if bp is None:
        return handlers
    for h in getattr(bp, "handlers", []) or []:
        handlers.append({
            "name": str(getattr(h, "name", "") or "handler"),
            "handler_type": str(getattr(h, "handler_type", "message") or "message"),
            "triggers": list(getattr(h, "triggers", []) or []),
            "description": str(getattr(h, "description", "") or ""),
        })
    return handlers


def start_reply_from_context(context: Any, commands: Sequence[Dict[str, Any]]) -> str:
    request = (getattr(context, "request", "") or "") if context else ""
    m = re.search(r"""/start[^\"'\n]{0,80}[\"']([^\"']+)[\"']""", request, re.I | re.S)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"""(?:يرسل|send|replies?|reply)\s*[:：]?\s*[\"']([^\"']+)[\"']""",
        request,
        re.I,
    )
    if m:
        return m.group(1).strip()

    # Explicit simple replies
    if re.search(r"hello\s*world", request, re.I):
        return "Hello World"
    if "هاي" in request and "إدارة" not in request and "ادارة" not in request:
        return "هاي"

    lines = ["تم تشغيل البوت."]
    if request.strip():
        first = request.strip().splitlines()[0].strip()
        if len(first) > 120:
            first = first[:117] + "..."
        lines.append(f"الطلب: {first}")
    if commands:
        lines.append("الأوامر:")
        for c in commands:
            if c["name"] == "start":
                continue
            desc = c.get("description") or ""
            if desc:
                lines.append(f"/{c['name']} — {desc}")
            else:
                lines.append(f"/{c['name']}")
    return "\n".join(lines)


def build_main_from_blueprint(
    *,
    framework: str,
    commands: Sequence[Dict[str, Any]],
    handlers: Sequence[Dict[str, Any]],
    start_reply: str,
) -> str:
    if framework == "aiogram":
        return _build_aiogram(commands, handlers, start_reply)
    return _build_ptb(commands, handlers, start_reply)


def _build_ptb(
    commands: Sequence[Dict[str, Any]],
    handlers: Sequence[Dict[str, Any]],
    start_reply: str,
) -> str:
    reply = repr(start_reply)
    fn_blocks: List[str] = []
    registers: List[str] = []

    for cmd in commands:
        name = cmd["name"]
        ident = _safe_ident(name)
        desc = cmd.get("description") or f"Command /{name}"
        admin = bool(cmd.get("admin_only"))
        group = bool(cmd.get("group_only"))

        if name == "start":
            body = (
                f"async def {ident}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
                f"    if update.message:\n"
                f"        await update.message.reply_text({reply})\n"
            )
        elif name == "help":
            help_lines = ["Available commands:"]
            for c in commands:
                help_lines.append(f"/{c['name']} — {c.get('description') or c['name']}")
            body = (
                f"async def {ident}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
                f"    if update.message:\n"
                f"        await update.message.reply_text({chr(10).join(help_lines)!r})\n"
            )
        else:
            guards = ""
            if group:
                guards += (
                    '    if update.effective_chat and update.effective_chat.type not in '
                    '("group", "supergroup"):\n'
                    '        await update.message.reply_text("This command is for groups only.")\n'
                    '        return\n'
                )
            if admin:
                guards += (
                    '    if update.effective_chat and update.effective_user:\n'
                    '        member = await context.bot.get_chat_member('
                    'update.effective_chat.id, update.effective_user.id)\n'
                    '        if member.status not in ("administrator", "creator"):\n'
                    '            await update.message.reply_text("Admins only.")\n'
                    '            return\n'
                )
            body = (
                f"async def {ident}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
                f"    if not update.message:\n"
                f"        return\n"
                f"{guards}"
                f"    args = context.args or []\n"
                f"    text = {desc!r}\n"
                f"    if args:\n"
                f"        text = text + \"\\nArgs: \" + \" \".join(args)\n"
                f"    await update.message.reply_text(text)\n"
            )
        fn_blocks.append(body)
        registers.append(f'    app.add_handler(CommandHandler("{name}", {ident}))')

    for h in handlers:
        hname = _safe_ident(h.get("name") or "on_message")
        triggers = h.get("triggers") or []
        if "new_chat_members" in triggers:
            fn_blocks.append(
                f"async def {hname}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
                f"    if not update.message or not update.message.new_chat_members:\n"
                f"        return\n"
                f"    for member in update.message.new_chat_members:\n"
                f"        if member.is_bot:\n"
                f"            continue\n"
                f"        await update.message.reply_text(\n"
                f"            f\"Welcome {{member.full_name}}!\"\n"
                f"        )\n"
            )
            registers.append(
                f"    app.add_handler(MessageHandler("
                f"filters.StatusUpdate.NEW_CHAT_MEMBERS, {hname}))"
            )

    return f'''"""Telegram bot entry point — assembled from blueprint commands/handlers.

Generated from understanding/planning output (CommandSpec / HandlerSpec).
Domain business logic should be filled by business-logic engines, not templates.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or .env file.")


{chr(10).join(fn_blocks)}

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
{chr(10).join(registers)}
    logger.info("Starting bot (polling) with %s command handler(s)", {len(commands)})
    app.run_polling()


if __name__ == "__main__":
    main()
'''


def _build_aiogram(
    commands: Sequence[Dict[str, Any]],
    handlers: Sequence[Dict[str, Any]],
    start_reply: str,
) -> str:
    reply = repr(start_reply)
    blocks: List[str] = []
    for cmd in commands:
        name = cmd["name"]
        ident = _safe_ident(name)
        desc = cmd.get("description") or f"/{name}"
        if name == "start":
            blocks.append(
                f"@dp.message(CommandStart())\n"
                f"async def {ident}(message: Message) -> None:\n"
                f"    await message.answer({reply})\n"
            )
        else:
            blocks.append(
                f'@dp.message(Command("{name}"))\n'
                f"async def {ident}(message: Message) -> None:\n"
                f"    await message.answer({desc!r})\n"
            )
    return f'''"""Telegram bot entry point (aiogram) — from blueprint commands."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or .env file.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


{chr(10).join(blocks)}

async def main() -> None:
    logger.info("Starting bot (aiogram polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
'''


def collect_class_sources(context: Any) -> Dict[str, str]:
    index: Dict[str, str] = {}
    if context is None:
        return index
    report = context.get("class_generation_report") if hasattr(context, "get") else None
    if report is None:
        return index
    classes = getattr(report, "classes", None) or getattr(report, "skeletons", None) or []
    for cls in classes:
        src = getattr(cls, "source_code", None) or ""
        if not src:
            continue
        path = getattr(cls, "path", None) or getattr(cls, "file_path", None) or ""
        name = getattr(cls, "name", None) or ""
        if path:
            index[str(path).replace("\\", "/").lstrip("/")] = str(src)
        if name:
            index[f"{name}.py"] = str(src)
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() + ".py"
            index[snake] = str(src)
    return index


def collect_features(context: Any) -> List[str]:
    return [c["name"] for c in extract_commands_from_context(context)]


def resolve_start_reply(request: str, features: List[str], fallback: str = "Hello World") -> str:
    class _Ctx:
        pass
    c = _Ctx()
    c.request = request
    c.get = lambda k, d=None: None
    commands = [{"name": f, "description": f} for f in features] or [
        {"name": "start", "description": "start"}
    ]
    return start_reply_from_context(c, commands) or fallback


def build_ptb_main(start_reply: str, features: List[str]) -> str:
    commands = [
        {"name": f, "description": f, "admin_only": False, "group_only": False}
        for f in features
    ]
    if not any(c["name"] == "start" for c in commands):
        commands.insert(0, {"name": "start", "description": "start"})
    return build_main_from_blueprint(
        framework="python-telegram-bot",
        commands=commands,
        handlers=[],
        start_reply=start_reply,
    )


def build_feature_module(stem: str) -> Optional[str]:
    return None
