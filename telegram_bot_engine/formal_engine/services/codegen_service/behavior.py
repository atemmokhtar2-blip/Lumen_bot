"""
behavior.py — fixed text templates REMOVED.

Surgical replacement: this module no longer emits domain service strings
or canned handler bodies. Code emission is owned by the Micro-Transpiler
(formal_engine.transpiler.micro).

Compatibility shims only — no template bodies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...schemas.program_contract import ProgramContract


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    if not s or s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _py(s: Any) -> str:
    return repr(s)


def snake_entity(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", (name or "").strip()).lower()
    return re.sub(r"[^a-z0-9_]", "_", s)[:40] or "item"


def resolve_service_for_command(
    cmd: str,
    service_names: list[str],
    entity_names: list[str],
) -> str | None:
    """Name-overlap only. No domain fallback templates."""
    cmd = (cmd or "").lower().strip()
    if not cmd:
        return None
    services = [s.lower() for s in service_names if s]
    if cmd in services:
        return cmd
    for s in services:
        if len(s) >= 3 and (s in cmd or cmd in s):
            return s
    return None


def primary_entity_fields(c: "ProgramContract") -> list[str]:
    return []


def field_prompts(fields: list[str], states_count: int) -> list[tuple[str, str]]:
    return []


def primary_entity_snake(c: "ProgramContract") -> str | None:
    return None


def emit_rich_service(name: str, responsibility: str = "") -> str:
    """No canned service body — micro-transpiler owns logic emission."""
    cls = "".join(p.capitalize() for p in _ident(name).split("_") if p) + "Service"
    return (
        f'"""Service {name} — synthesized stub (use formal pipeline for full logic)."""\n'
        "from __future__ import annotations\n"
        "from typing import Any\n\n\n"
        f"class {cls}:\n"
        "    def __init__(self, repo: Any = None) -> None:\n"
        "        self._repo = repo\n\n"
        "    async def handle(self, user_id: int = 0, args: list | None = None, payload: dict | None = None) -> str:\n"
        "        return \"ok\"\n"
    )


def emit_messages_ptb(c: "ProgramContract") -> str:
    """Deprecated template path — empty formal-safe handler."""
    return (
        '"""messages — use formal Micro-Transpiler path."""\n'
        "from __future__ import annotations\n"
        "from telegram import Update\n"
        "from telegram.ext import ContextTypes\n\n\n"
        "async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
        "    message = update.effective_message\n"
        "    if message is None:\n"
        "        return\n"
        "    await message.reply_text(\"use formal pipeline\")\n"
    )


def emit_messages_aiogram(c: "ProgramContract") -> str:
    return (
        '"""messages aiogram — use formal Micro-Transpiler path."""\n'
        "from __future__ import annotations\n\n\n"
        "async def message_handler(message) -> None:\n"
        "    await message.answer(\"use formal pipeline\")\n"
    )


def emit_cmd_aiogram(cmd_name: str, description: str = "", service_name: str | None = None) -> str:
    fn = _ident(cmd_name) + "_handler"
    return (
        f'"""cmd {cmd_name} — use formal path."""\n'
        "from __future__ import annotations\n\n\n"
        f"async def {fn}(message) -> None:\n"
        f"    await message.answer({_py(cmd_name)})\n"
    )


def emit_callbacks_aiogram(c: "ProgramContract") -> str:
    return (
        '"""callbacks — use formal Micro-Transpiler path."""\n'
        "from __future__ import annotations\n\n\n"
        "async def callback_handler(callback) -> None:\n"
        "    await callback.answer()\n"
    )
