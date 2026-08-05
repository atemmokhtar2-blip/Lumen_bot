"""
Structural helpers for codegen — NO domain tables, NO tag→command maps.

Commands / buttons / services / entities come exclusively from ProgramContract.
"""

from __future__ import annotations

from ...schemas.program_contract import CommandUnit, ProgramContract


def effective_commands(c: ProgramContract) -> list[CommandUnit]:
    by_name: dict[str, CommandUnit] = {cmd.name: cmd for cmd in c.commands}
    if "start" not in by_name:
        by_name["start"] = CommandUnit(name="start", description="start", admin_only=False)
    if "help" not in by_name:
        by_name["help"] = CommandUnit(name="help", description="help", admin_only=False)
    ordered: list[CommandUnit] = []
    for n in ("start", "help"):
        ordered.append(by_name.pop(n))
    ordered.extend(sorted(by_name.values(), key=lambda x: x.name))
    return ordered


def effective_buttons(c: ProgramContract):
    return list(c.buttons or [])


def effective_services(c: ProgramContract):
    return list(c.services or [])


def welcome_text(c: ProgramContract) -> str:
    name = (c.bot_name or "Bot").strip()
    return f"مرحباً بك في {name}\nاستخدم /help لعرض الأوامر المتاحة."


def help_text(commands: list[CommandUnit]) -> str:
    lines = [f"/{c.name} — {c.description or c.name}" for c in commands]
    return "\n".join(lines) if lines else "/start — start"
