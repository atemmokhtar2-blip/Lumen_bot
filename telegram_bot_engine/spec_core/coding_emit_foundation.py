"""Emit foundation: config + SQLite schema for generated bots."""
from __future__ import annotations

from .schema import BotSpec, Feature
from .registry import get_capability


def _msg(feat: Feature, kind: str, default: str) -> str:
    if kind == "success":
        return feat.messages.success or feat.success.get("message") or default
    if kind == "failure":
        return feat.messages.failure or feat.failure.get("message") or default
    return feat.messages.prompt or default


def _emit_config() -> str:
    return '''"""Runtime settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return frozenset(out)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = ""
    payment_provider_token: str = ""
    admin_user_ids: frozenset[int] = field(default_factory=frozenset)
    default_currency: str = "USD"

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
            payment_provider_token=(os.getenv("PAYMENT_PROVIDER_TOKEN") or "").strip(),
            admin_user_ids=_parse_ids(os.getenv("ADMIN_USER_IDS") or ""),
            default_currency=(os.getenv("DEFAULT_CURRENCY") or "USD").strip().upper() or "USD",
        )

    def is_admin(self, user_id: int) -> bool:
        return int(user_id) in self.admin_user_ids


def get_settings() -> Settings:
    return Settings.load()
'''


def _emit_models(spec: BotSpec) -> str:
    """Emit a stable, dependency-free model contract for generated projects."""
    lines = [
        '"""Generated domain models; persistence remains in app.db services."""',
        "from __future__ import annotations",
        "from dataclasses import dataclass",
        "",
    ]
    entities = list(getattr(spec, "entities", None) or [])
    if not entities:
        entities = []
    for entity in entities:
        raw_name = str(getattr(entity, "name", "Entity") or "Entity")
        name = "".join(ch for ch in raw_name.title() if ch.isalnum()) or "Entity"
        lines += ["@dataclass", f"class {name}:", "    id: int | None = None"]
        for field in list(getattr(entity, "fields", None) or []):
            field_name = "".join(ch for ch in str(getattr(field, "name", "field")) if ch.isalnum() or ch == "_")
            if not field_name or field_name[0].isdigit() or field_name == "id":
                continue
            field_type = str(getattr(field, "type", "str") or "str")
            py_type = {"int": "int", "float": "float", "bool": "bool"}.get(field_type, "str")
            lines.append(f"    {field_name}: {py_type} | None = None")
        lines.append("")
    if not entities:
        lines += ["@dataclass", "class User:", "    id: int | None = None", "    name: str | None = None", ""]
    return "\n".join(lines).rstrip() + "\n"


def _emit_db(spec: BotSpec) -> str:
    need = spec.storage.type == "sqlite" or any(
        (get_capability(f.feature) and get_capability(f.feature).service in {"tasks", "notes", "welcome", "tickets", "security", "shop", "booking", "crm", "reminders", "community", "edu", "hr", "utils", "gate", "payments", "subscriptions", "points", "contests", "cart", "growth", "wallet", "creator", "i18n", "analytics", "compliance", "forms", "events", "jobs", "marketplace", "restaurant", "support", "admin", "notify"})  # type: ignore[union-attr]
        for f in spec.features
    )
    if not need:
        return ""
    return '''"""SQLite helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent.parent / "data.sqlite3"


def connect() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'medium',
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                message TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                subject TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_staff INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extras_kv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                stock INTEGER NOT NULL DEFAULT 100,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL DEFAULT 0,
                amount_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'pending',
                payload TEXT NOT NULL DEFAULT '',
                charge_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price_cents INTEGER NOT NULL DEFAULT 0,
                duration_days INTEGER NOT NULL DEFAULT 30,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                starts_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ends_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS point_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                winner_user_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contest_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE(contest_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                invited_by INTEGER NOT NULL DEFAULT 0,
                rewards INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_lang (
                user_id INTEGER PRIMARY KEY,
                lang TEXT NOT NULL DEFAULT 'en'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL DEFAULT 0,
                amount_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                provider_charge_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id)
            )
            """
        )
        conn.commit()
'''


