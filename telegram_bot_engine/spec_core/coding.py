"""Coding Engine — emits python-telegram-bot v21 project files from BotSpec (no AI).

Split modules:
  - coding_emit_foundation: config + db
  - coding_emit_services: moderation/tasks/notes/tickets/security/extras/...
  - coding_handlers: keyboards + per-feature handlers + main.py
  - templates_generic / templates_market: service runtimes
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .coding_emit_foundation import _emit_config, _emit_db
from .coding_emit_services import (
    _emit_content,
    _emit_extras,
    _emit_moderation,
    _emit_notes,
    _emit_security,
    _emit_tasks,
    _emit_tickets,
    _emit_welcome,
)
from .coding_handlers import _emit_handlers, _emit_keyboards, _emit_main
from .planning import plan_from_spec
from .schema import BotSpec


def _emit_market() -> str:
    path = Path(__file__).resolve().parent / "templates_market.py"
    return path.read_text(encoding="utf-8")


def _emit_generic_runtime() -> str:
    path = Path(__file__).resolve().parent / "templates_generic.py"
    return path.read_text(encoding="utf-8")


def generate_files(spec: BotSpec) -> dict[str, str]:
    plan = plan_from_spec(spec)
    services = list(plan.services)
    files: dict[str, str] = {
        "app/__init__.py": "",
        "app/config.py": _emit_config(),
        "app/db.py": _emit_db(spec),
        "app/keyboards.py": _emit_keyboards(spec),
        "app/handlers.py": _emit_handlers(spec),
        "main.py": _emit_main(spec),
        "requirements.txt": "python-telegram-bot==21.6\npython-dotenv>=1.0.0\n",
        ".env.example": "TELEGRAM_BOT_TOKEN=\nADMIN_IDS=\n",
        "README.md": f"# {spec.bot.name}\n\nZero-AI generated Telegram bot.\n\n1. cp .env.example .env\n2. Set TELEGRAM_BOT_TOKEN\n3. pip install -r requirements.txt\n4. python main.py\n",
    }
    files["app/services/__init__.py"] = ""
    # Optional services based on plan
    svc_set = set(services)
    if "moderation" in svc_set or "admin" in svc_set:
        files["app/services/moderation.py"] = _emit_moderation()
    if "tasks" in svc_set:
        files["app/services/tasks.py"] = _emit_tasks()
    if "notes" in svc_set:
        files["app/services/notes.py"] = _emit_notes()
    if "welcome" in svc_set:
        files["app/services/welcome.py"] = _emit_welcome()
    if "tickets" in svc_set or "support" in svc_set:
        files["app/services/tickets.py"] = _emit_tickets()
    if "security" in svc_set:
        files["app/services/security.py"] = _emit_security()
    if "content" in svc_set:
        files["app/services/content.py"] = _emit_content(spec)
    if any(x in svc_set for x in (
        "utils", "extras", "clinic", "jobs", "edu", "events", "restaurant", "auction",
        "delivery", "crm", "booking", "community", "hr", "marketplace", "fitness",
        "realestate", "shop", "cart", "wallet", "points", "growth", "subscriptions",
        "payments", "contests", "i18n", "analytics", "admin", "gate",
    )):
        files["app/services/extras.py"] = _emit_extras()
    if {
        "shop", "payments", "subscriptions", "points", "contests", "cart",
        "growth", "wallet", "i18n", "creator",
    } & svc_set:
        files["app/services/market.py"] = _emit_market()
    if spec.storage.type == "sqlite" or len(spec.features) > 2:
        if files.get("app/db.py"):
            files["app/services/generic.py"] = _emit_generic_runtime()
    return files


def write_project(spec: BotSpec, out_dir: str | Path) -> list[str]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, content in generate_files(spec).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        written.append(str(path))
    return written


__all__ = ["generate_files", "write_project"]
