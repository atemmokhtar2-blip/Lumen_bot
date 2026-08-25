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
    return '''"""Runtime settings — loaded once from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

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
        # Accept ADMIN_IDS as alias of ADMIN_USER_IDS (common user typo)
        admins = os.getenv("ADMIN_USER_IDS") or os.getenv("ADMIN_IDS") or ""
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
        return cls(
            telegram_bot_token=token,
            payment_provider_token=(os.getenv("PAYMENT_PROVIDER_TOKEN") or "").strip(),
            admin_user_ids=_parse_ids(admins),
            default_currency=(os.getenv("DEFAULT_CURRENCY") or "USD").strip().upper() or "USD",
        )

    def require_token(self) -> str:
        """Return token or raise a clear configuration error (never log the secret)."""
        if not self.telegram_bot_token or ":" not in self.telegram_bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is missing or invalid. "
                "Copy .env.example → .env and set a BotFather token."
            )
        return self.telegram_bot_token

    def is_admin(self, user_id: int) -> bool:
        try:
            return int(user_id) in self.admin_user_ids
        except (TypeError, ValueError):
            return False


@lru_cache(maxsize=1)
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
    """Emit SQLite helpers sized to the selected services only."""
    services: set[str] = set()
    try:
        from .registry import get_capability

        for f in spec.features or []:
            cap = get_capability(getattr(f, "feature", ""))
            if cap and getattr(cap, "service", None):
                services.add(str(cap.service))
    except Exception:
        pass

    need_tasks = "tasks" in services
    need_booking = (
        "booking" in services
        or any(str(getattr(f, "feature", "")).startswith("book_") for f in (spec.features or []))
    )
    need_clinic = (
        "clinic" in services
        or any(str(getattr(f, "feature", "")).startswith("clinic_") for f in (spec.features or []))
    )
    need_reminders = (
        "reminders" in services or "scheduler" in services
        or any(str(getattr(f, "feature", "")).startswith("remind_") for f in (spec.features or []))
    )
    need_notes = "notes" in services
    need_welcome = "welcome" in services
    need_tickets = bool(services & {"tickets", "support"})
    need_security = "security" in services
    need_market = bool(
        services
        & {
            "shop",
            "payments",
            "subscriptions",
            "points",
            "contests",
            "cart",
            "growth",
            "wallet",
            "analytics",
            "admin",
            "market",
            "creator",
        }
    )
    if not need_market:
        _mkeys = (
            "shop", "cart", "wallet", "order", "product", "coupon", "payment",
            "invoice", "checkout", "wishlist", "review", "shipping", "stock",
            "plan", "sub", "contest", "points", "balance", "catalog",
        )
        for feat in spec.features or []:
            fk = str(getattr(feat, "feature", "") or "").lower()
            if any(k in fk for k in _mkeys):
                need_market = True
                break
    need_extras = bool(
        services
        & {
            "utils",
            "extras",
            "clinic",
            "jobs",
            "edu",
            "events",
            "restaurant",
            "auction",
            "delivery",
            "crm",
            "booking",
            "community",
            "hr",
            "marketplace",
            "fitness",
            "realestate",
        }
    )

    table_sql: list[str] = [
        "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    ]
    if need_tasks:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "title TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', "
            "priority TEXT NOT NULL DEFAULT 'medium', "
            "done INTEGER NOT NULL DEFAULT 0)"
        )
    if need_notes:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS notes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "body TEXT NOT NULL)"
        )
    if need_reminders:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS reminders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "chat_id INTEGER NOT NULL DEFAULT 0, "
            "body TEXT NOT NULL, "
            "due_ts INTEGER NOT NULL DEFAULT 0, "
            "fired INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_booking:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS bookings ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "chat_id INTEGER NOT NULL DEFAULT 0, "
            "body TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_clinic:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS clinic_appts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "chat_id INTEGER NOT NULL DEFAULT 0, "
            "body TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_welcome:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS welcome_settings ("
            "chat_id INTEGER PRIMARY KEY, "
            "enabled INTEGER NOT NULL DEFAULT 1, "
            "message TEXT NOT NULL DEFAULT '')"
        )
    if need_tickets:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS tickets ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "chat_id INTEGER NOT NULL DEFAULT 0, "
            "subject TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS ticket_messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ticket_id INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, "
            "is_staff INTEGER NOT NULL DEFAULT 0, "
            "body TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_security:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS security_reports ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL, "
            "kind TEXT NOT NULL, "
            "body TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_extras:
        table_sql.append(
            "CREATE TABLE IF NOT EXISTS extras_kv ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id INTEGER NOT NULL DEFAULT 0, "
            "kind TEXT NOT NULL, "
            "body TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'open', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    if need_market:
        # Always include extras_kv for roles/feedback used by market enterprise helpers
        if not need_extras:
            table_sql.append(
                "CREATE TABLE IF NOT EXISTS extras_kv ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER NOT NULL DEFAULT 0, "
                "kind TEXT NOT NULL, "
                "body TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'open', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        table_sql.extend(
            [
                "CREATE TABLE IF NOT EXISTS products ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                "price_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'USD', "
                "stock INTEGER NOT NULL DEFAULT 100, active INTEGER NOT NULL DEFAULT 1, "
                "description TEXT NOT NULL DEFAULT '', vendor_id INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "product_id INTEGER NOT NULL DEFAULT 0, amount_cents INTEGER NOT NULL DEFAULT 0, "
                "currency TEXT NOT NULL DEFAULT 'USD', status TEXT NOT NULL DEFAULT 'pending', "
                "payload TEXT NOT NULL DEFAULT '', charge_id TEXT NOT NULL DEFAULT '', "
                "coupon_code TEXT NOT NULL DEFAULT '', stock_reserved INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS cart_items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "product_id INTEGER NOT NULL, qty INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE(user_id, product_id))",
                "CREATE TABLE IF NOT EXISTS point_ledger ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "delta INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS wallets ("
                "user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS wallet_ledger ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "amount INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS plans ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                "price_cents INTEGER NOT NULL DEFAULT 0, duration_days INTEGER NOT NULL DEFAULT 30, "
                "active INTEGER NOT NULL DEFAULT 1)",
                "CREATE TABLE IF NOT EXISTS subscriptions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "plan_id INTEGER NOT NULL, expires_at TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'active', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS payments ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "order_id INTEGER NOT NULL DEFAULT 0, amount_cents INTEGER NOT NULL DEFAULT 0, "
                "currency TEXT NOT NULL DEFAULT 'USD', "
                "provider_charge_id TEXT NOT NULL DEFAULT '', "
                "payload TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_charge "
                "ON payments(provider_charge_id) WHERE provider_charge_id != ''",
                "CREATE TABLE IF NOT EXISTS vodafone_payments ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "amount_cents INTEGER NOT NULL DEFAULT 0, phone TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL DEFAULT 'pending', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS reviews ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "product_id INTEGER NOT NULL, rating INTEGER NOT NULL DEFAULT 5, "
                "body TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS coupons ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, "
                "percent_off REAL NOT NULL DEFAULT 0, amount_off_cents INTEGER NOT NULL DEFAULT 0, "
                "max_uses INTEGER NOT NULL DEFAULT 100, used INTEGER NOT NULL DEFAULT 0, "
                "active INTEGER NOT NULL DEFAULT 1, expires_at TEXT, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS coupon_redemptions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, coupon_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, order_id INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS order_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, "
                "status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', "
                "actor_id INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS audit_log ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER NOT NULL DEFAULT 0, "
                "action TEXT NOT NULL, entity TEXT NOT NULL DEFAULT '', "
                "entity_id INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '', "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS stock_moves ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, "
                "delta INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', "
                "actor_id INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS contests ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'open', winner_id INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS contest_entries ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, contest_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, UNIQUE(contest_id, user_id))",
                "CREATE TABLE IF NOT EXISTS wishlist ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "product_id INTEGER NOT NULL, UNIQUE(user_id, product_id))",
                "CREATE TABLE IF NOT EXISTS referrals ("
                "user_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, "
                "invited_by INTEGER NOT NULL DEFAULT 0, rewards INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS user_lang ("
                "user_id INTEGER PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'ar')",
                "CREATE TABLE IF NOT EXISTS saas_tenants ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                "owner_id INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS vendors ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE, "
                "name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active')",
            ]
        )

    exec_lines = []
    for sql in table_sql:
        exec_lines.append(f"        conn.execute({sql!r})")
    body = "\n".join(exec_lines)

    return (
        '"""SQLite helpers — schema matches selected bot services only."""\n'
        "from __future__ import annotations\n\n"
        "import sqlite3\n"
        "from pathlib import Path\n\n"
        "_DB = Path(__file__).resolve().parent.parent / \"data.sqlite3\"\n\n\n"
        "def connect() -> sqlite3.Connection:\n"
        "    _DB.parent.mkdir(parents=True, exist_ok=True)\n"
        "    conn = sqlite3.connect(_DB, check_same_thread=False, timeout=30)\n"
        "    conn.row_factory = sqlite3.Row\n"
        "    try:\n"
        "        conn.execute(\"PRAGMA journal_mode=WAL\")\n"
        "        conn.execute(\"PRAGMA synchronous=NORMAL\")\n"
        "    except sqlite3.Error:\n"
        "        pass\n"
        "    return conn\n\n\n"
        "def init_db() -> None:\n"
        "    with connect() as conn:\n"
        + body
        + "\n        conn.commit()\n"
    )
