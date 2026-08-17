"""Coding Engine — emits python-telegram-bot v21 project files from BotSpec (no AI).

Split modules:
  - coding_emit_foundation: config + db
  - coding_emit_services: moderation/tasks/notes/tickets/security/extras/...
  - coding_handlers: keyboards + per-feature handlers + main.py
  - templates_generic / templates_market: service runtimes
"""
from __future__ import annotations

def _emit_bootstrap_sh() -> str:
    return """#!/usr/bin/env bash
set -e
echo "Bootstrapping Telegram bot..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 required"; exit 1
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || true
  echo "Edit .env and set TELEGRAM_BOT_TOKEN then re-run."
  exit 1
fi
python main.py
"""

from pathlib import Path
from typing import Any

from .coding_emit_foundation import _emit_config, _emit_db, _emit_models
from .coding_emit_services import _emit_reminders_service, _emit_booking_service, _emit_clinic_service, _emit_lean_generic_service, _emit_lean_named_service, _emit_content, _emit_extras, _emit_moderation, _emit_notes, _emit_security, _emit_tasks, _emit_tickets, _emit_welcome, _emit_pubg
from .templates_sentry import emit_sentry_setup
from .coding_handlers import _emit_handlers, _emit_keyboards, _emit_main
from .planning import plan_from_spec
from .schema import BotSpec



def _emit_flow_engine() -> str:
    path = Path(__file__).resolve().parent / "templates_flow_engine.py"
    return path.read_text(encoding="utf-8")

def _emit_market() -> str:
    path = Path(__file__).resolve().parent / "runtime" / "market_runtime.py"
    return path.read_text(encoding="utf-8")


def _emit_generic_runtime() -> str:
    path = Path(__file__).resolve().parent / "runtime" / "generic_runtime.py"
    return path.read_text(encoding="utf-8")


def _emit_generic_runtime_data() -> str:
    """Return the generic runtime JSON catalog for generated projects."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "data" / "templates" / "generic_runtime.json",  # telegram_bot_engine/data/...
        here.parents[2] / "data" / "templates" / "generic_runtime.json",  # repo root /data/...
        here.parent / "runtime" / "generic_runtime.json",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "generic_runtime.json not found; expected under telegram_bot_engine/data/templates/"
    )



def _emit_i18n_service() -> str:
    """Minimal language preference store — no market pack required."""
    return '''"""Lightweight per-user language preferences."""
from __future__ import annotations

from typing import Dict

_LANG: Dict[int, str] = {}


def get_lang(user_id: int) -> str:
    return _LANG.get(int(user_id), "ar")


def set_lang(user_id: str | int, lang: str) -> str:
    code = (lang or "ar").strip().lower()[:2] or "ar"
    if code not in {"ar", "en"}:
        code = "ar"
    _LANG[int(user_id)] = code
    return code
'''


def _emit_gitignore() -> str:
    return """# Generated Telegram bot
.env
.venv/
venv/
__pycache__/
*.py[cod]
*.sqlite3
*.db
.pytest_cache/
.mypy_cache/
.DS_Store
.tbe_bot_token
.deploy_*.log
"""


def _emit_readme(spec: BotSpec) -> str:
    name = getattr(spec.bot, "name", None) or "telegram-bot"
    cmds = []
    for f in spec.features:
        if getattr(getattr(f, "trigger", None), "type", None) == "command":
            cid = getattr(f.trigger, "id", "") or ""
            if cid:
                cmds.append(f"- `/{cid}` — {getattr(f, 'feature', cid)}")
    cmd_block = "\n".join(cmds) if cmds else "- `/start`\n- `/help`"
    return f"""# {name}

Professional Telegram bot generated without AI codegen templates dumping.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN in .env
python main.py
```

## Commands

{cmd_block}

## Structure

- `main.py` — application entry (python-telegram-bot v21)
- `app/handlers.py` — command handlers
- `app/keyboards.py` — inline keyboards
- `app/config.py` — settings from environment

## Security

- Never commit `.env` or bot tokens
- Rotate tokens if exposed
"""


def _feature_services(spec: BotSpec) -> set[str]:
    try:
        from .registry import get_capability
    except Exception:
        return set()
    out: set[str] = set()
    for f in spec.features:
        try:
            cap = get_capability(f.feature)
            if cap and getattr(cap, "service", None):
                out.add(cap.service)
        except Exception:
            continue
    return out


_MARKET_SERVICES = {
    "shop", "payments", "subscriptions", "points", "contests",
    "cart", "growth", "wallet", "analytics", "admin",
}
_FLOW_HINTS = {
    "shop", "payments", "cart", "wallet", "booking", "tickets", "crm",
    # notes/tasks use simple awaiting flags — not the full flow_engine pack
}
_GENERIC_HINTS = {
    "generic", "booking", "crm", "community", "edu", "hr", "marketplace",
    "fitness", "realestate", "restaurant", "auction", "delivery",
}



def _emit_quality_tests() -> str:
    """Smoke tests shipped with every generated bot (no network, no token)."""
    return '''"""Smoke tests for the generated bot (offline)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_python_files_parse() -> None:
    py_files = list(ROOT.rglob("*.py"))
    assert py_files, "no python files"
    for path in py_files:
        if ".venv" in path.parts or "venv" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        ast.parse(src, filename=str(path))


def test_handlers_define_start_and_help() -> None:
    handlers = ROOT / "app" / "handlers.py"
    assert handlers.is_file()
    src = handlers.read_text(encoding="utf-8")
    assert "async def start_handler" in src
    assert "async def help_handler" in src


def test_no_hardcoded_bot_token() -> None:
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Telegram tokens look like 123456789:AA...
        assert ":AA" not in text and ":AB" not in text or "example" in text.lower()
'''


def _emit_env_example() -> str:
    return (
        "# Telegram bot token from @BotFather (never commit the real value)\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "# Comma-separated Telegram user ids with admin powers\n"
        "ADMIN_USER_IDS=\n"
        "ADMIN_IDS=\n"
        "DEFAULT_CURRENCY=USD\n"
    )



def _emit_db_slim() -> str:
    """Tiny SQLite helper for bots that do not need the commerce schema."""
    return '''"""Minimal database helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent.parent / "bot_data.sqlite3"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.commit()
'''

def generate_files(spec: BotSpec) -> dict[str, str]:
    plan = plan_from_spec(spec)
    services = list(plan.services)
    files: dict[str, str] = {
        "app/__init__.py": "",
        "app/config.py": _emit_config(),
        "app/sentry_setup.py": emit_sentry_setup(),
        "app/db.py": _emit_db(spec),
        "app/models.py": _emit_models(spec),
        "app/keyboards.py": _emit_keyboards(spec),
        "app/handlers.py": _emit_handlers(spec),
        "main.py": _emit_main(spec),
        "requirements.txt": "python-telegram-bot==21.6\npython-dotenv>=1.0.0\n",
        ".env.example": "TELEGRAM_BOT_TOKEN=\nADMIN_USER_IDS=\nADMIN_IDS=\nDEFAULT_CURRENCY=USD\n",
        "README.md": f"# {spec.bot.name}\n\nZero-AI generated Telegram bot.\n\n1. cp .env.example .env\n2. Set TELEGRAM_BOT_TOKEN\n3. pip install -r requirements.txt\n4. python main.py\n",
    }
    files["app/services/__init__.py"] = ""
    files[".gitignore"] = _emit_gitignore()
    files["README.md"] = _emit_readme(spec)
    files[".env.example"] = _emit_env_example()
    files["tests/test_smoke.py"] = _emit_quality_tests()
    files["tests/__init__.py"] = ""
    svc_set = set(services) | _feature_services(spec)
    # Feature-gated heavy modules (avoid dumping full market pack on simple bots)
    needs_market = bool(svc_set & _MARKET_SERVICES)
    needs_flow = bool(svc_set & _FLOW_HINTS) or needs_market
    needs_generic = bool(svc_set & _GENERIC_HINTS)
    needs_tickets = "tickets" in svc_set or "support" in svc_set
    needs_lang = any(
        (getattr(f, "feature", "") in {"lang", "language", "set_language"})
        or (getattr(getattr(f, "trigger", None), "id", "") == "lang")
        for f in spec.features
    )
    if needs_lang or not needs_market:
        files["app/services/i18n.py"] = _emit_i18n_service()
    if needs_market:
        files["app/services/market.py"] = _emit_market()
    if needs_flow:
        files["app/flow_engine.py"] = _emit_flow_engine()
    if needs_tickets:
        files["app/services/tickets.py"] = _emit_tickets()
    feat_keys_early = {getattr(f, "feature", "") for f in (spec.features or [])}
    only_basic_early = feat_keys_early <= {
        "start", "help", "about", "lang", "language", "explicit_command", "",
    }
    if only_basic_early and not needs_market:
        files["app/db.py"] = _emit_db_slim()
    elif needs_market:
        # Always force full commerce schema when market is present
        files["app/db.py"] = _emit_db(spec)
    if needs_generic and not only_basic_early:
        files["app/services/generic.py"] = _emit_generic_runtime()
        try:
            files["app/services/generic_runtime.json"] = _emit_generic_runtime_data()
        except FileNotFoundError:
            pass
    # db only when storage or services need persistence
    if spec.storage.type == "none" and not (needs_market or needs_tickets or needs_generic or needs_flow):
        # keep a minimal models module; db can stay for future but prefer slim —
        # still emit db for import safety only if handlers reference it
        pass
    if "moderation" in svc_set or "admin" in svc_set:
        files["app/services/moderation.py"] = _emit_moderation()
    if "pubg" in svc_set or any(
        str(getattr(f, "feature", "")).startswith("pubg_") for f in (spec.features or [])
    ):
        files["app/services/pubg.py"] = _emit_pubg()
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
        "payments", "contests", "analytics", "admin", "gate",
    )):
        files["app/services/extras.py"] = _emit_extras()
    # Late safety: only attach heavy runtimes when services truly need them
    late_flow = bool(
        {
            "shop", "payments", "subscriptions", "points", "contests", "cart",
            "growth", "wallet", "creator", "tickets", "support",
        }
        & svc_set
    )
    if late_flow:
        files.setdefault("app/flow_engine.py", _emit_flow_engine())
        if {"shop", "payments", "subscriptions", "points", "contests", "cart",
            "growth", "wallet", "creator"} & svc_set:
            files.setdefault("app/services/market.py", _emit_market())
        if {"tickets", "support"} & svc_set:
            files.setdefault("app/services/tickets.py", _emit_tickets())
    # generic only for real generic/utility backends — NOT merely because feature count > 2
    if ({"translate", "ocr", "scheduler", "utils"} & svc_set) or (
        "generic" in svc_set and not only_basic_early
    ):
        files["app/services/generic.py"] = _emit_generic_runtime()
        try:
            files.setdefault(
                "app/services/generic_runtime.json",
                _emit_generic_runtime_data(),
            )
        except FileNotFoundError:
            pass

    files.setdefault("bootstrap.sh", _emit_bootstrap_sh())

    # ── HARD GATE: shop/market bots MUST ship full commerce schema ──
    if "app/services/market.py" in files:
        db_body = files.get("app/db.py") or ""
        required = ("wallets", "plans", "extras_kv", "products", "orders", "payments")
        if any(t not in db_body for t in required):
            files["app/db.py"] = _emit_db(spec)
            db_body = files["app/db.py"]
        if any(t not in db_body for t in required):
            # absolute fallback: append CREATE statements via market ensure path
            files["app/db.py"] = _emit_db(spec)
        mkt = files.get("app/services/market.py") or ""
        if "CREATE TABLE IF NOT EXISTS wallets" not in mkt:
            files["app/services/market.py"] = _emit_market()
            mkt = files["app/services/market.py"]
        if "CREATE TABLE IF NOT EXISTS wallets" not in mkt:
            raise RuntimeError("market_schema_gate_failed: market.py missing wallets DDL")
        if any(t not in files["app/db.py"] for t in required):
            raise RuntimeError(
                "market_schema_gate_failed: db.py missing "
                + ",".join(t for t in required if t not in files["app/db.py"])
            )


    # Phase 11: optional production backends for translate / OCR / schedule
    req_lines = ["python-telegram-bot==21.6", "python-dotenv>=1.0.0", "sentry-sdk>=2.0.0"]
    opt_req: list[str] = []
    env_lines = ["TELEGRAM_BOT_TOKEN=", "ADMIN_IDS="]
    readme_extra: list[str] = []
    feat_keys = {getattr(f, "feature", "") for f in (spec.features or [])}
    needs_translate = (
        "translate" in svc_set
        or any(str(k).startswith("scaffold_translate") for k in feat_keys)
    )
    needs_ocr = (
        "ocr" in svc_set
        or any(str(k).startswith("scaffold_ocr") for k in feat_keys)
    )
    needs_sched = (
        "scheduler" in svc_set
        or "reminders" in svc_set
        or any(str(k).startswith("scaffold_schedule") for k in feat_keys)
    )
    needs_payinfo = any(str(k).startswith("scaffold_payment") for k in feat_keys)
    if not needs_payinfo:
        try:
            from .registry import get_capability as _gc_pay
            for _k in feat_keys:
                _c = _gc_pay(str(_k))
                if _c and getattr(_c, "method", "") in {"payment_info", "pay_info"}:
                    needs_payinfo = True
                    break
        except Exception:
            pass
    if needs_translate:
        opt_req.append("deep-translator>=1.11.4")
        env_lines += [
            "TRANSLATE_BACKEND=echo",
            "TRANSLATE_TARGET=ar",
            "TRANSLATE_API_URL=http://localhost:5000",
            "TRANSLATE_API_KEY=",
            "TRANSLATE_TIMEOUT=8",
        ]
        readme_extra += [
            "### Translate",
            "```bash",
            "pip install -r requirements-optional.txt",
            "# or: pip install deep-translator",
            "```",
            "Set `TRANSLATE_BACKEND=deep-translator` or `libre`.",
            "For LibreTranslate: `TRANSLATE_API_URL` + optional `TRANSLATE_API_KEY`.",
            "Check status: `/translate status`",
        ]
    if needs_ocr:
        opt_req += ["pytesseract>=0.3.10", "Pillow>=10.0.0"]
        env_lines += [
            "OCR_ENABLED=1",
            "OCR_LANG=eng+ara",
        ]
        readme_extra += [
            "### OCR",
            "```bash",
            "pip install pytesseract Pillow",
            "# system: apt install tesseract-ocr tesseract-ocr-ara",
            "```",
            "Env: `OCR_ENABLED=1`, `OCR_LANG=eng+ara`",
        ]
    if needs_payinfo:
        env_lines += [
            "PAYMENT_VODAFONE_CASH=",
            "PAYMENT_INSTAPAY=",
            "PAYMENT_BANK_IBAN=",
            "PAYMENT_WALLET=",
            "PAYMENT_INSTRUCTIONS=",
        ]
        readme_extra += [
            "### Payment info",
            "Set PAYMENT_VODAFONE_CASH / PAYMENT_INSTAPAY / PAYMENT_BANK_IBAN / PAYMENT_WALLET / PAYMENT_INSTRUCTIONS in .env",
        ]
    if needs_sched:
        # PTB JobQueue extra (APScheduler)
        opt_req.append("python-telegram-bot[job-queue]==21.6")
        env_lines += [
            "SCHEDULE_ENABLED=1",
            "SCHEDULE_BATCH_LIMIT=20",
        ]
        readme_extra += [
            "### Schedule",
            "`/schedule in 5m text` or `/schedule بعد 10 دقائق نص` stores due_ts + chat_id.",
            "Supports: بعد نصف ساعة / بعد ساعة / in 90s / بعد يومين …",
            "main.py polls JobQueue every 60s when SCHEDULE_ENABLED=1.",
            "SCHEDULE_BATCH_LIMIT caps deliveries per tick (default 20).",
            "Requires: pip install 'python-telegram-bot[job-queue]==21.6'",
        ]
    files["requirements.txt"] = "\n".join(req_lines) + "\n"
    if opt_req:
        files["requirements-optional.txt"] = (
            "# Optional production backends — install when ready\n"
            + "\n".join(opt_req)
            + "\n"
        )
        # keep comments in main requirements pointing to optional file
        files["requirements.txt"] += (
            "# Optional backends: pip install -r requirements-optional.txt\n"
        )
    files[".env.example"] = "\n".join(env_lines) + "\n"
    if readme_extra:
        base_readme = files.get("README.md") or ""
        files["README.md"] = (
            base_readme
            + "\n## Optional backends (Phase 11)\n\n"
            + "\n".join(readme_extra)
            + "\n"
        )
    # Augment config.py with backend settings helpers
    if needs_translate or needs_ocr:
        cfg = files.get("app/config.py") or ""
        if "backend_env_snapshot" not in cfg:
            cfg += (
                "\n\n# --- Phase 11 optional backends ---\n"
                "def backend_env_snapshot() -> dict[str, str]:\n"
                "    keys = [\n"
                "        \"TRANSLATE_BACKEND\", \"TRANSLATE_TARGET\", \"TRANSLATE_API_URL\",\n"
                "        \"TRANSLATE_API_KEY\", \"TRANSLATE_TIMEOUT\",\n"
                "        \"OCR_ENABLED\", \"OCR_LANG\",\n"
                "    ]\n"
                "    out: dict[str, str] = {}\n"
                "    for k in keys:\n"
                "        v = (os.getenv(k) or \"\").strip()\n"
                "        if k.endswith(\"KEY\") and v:\n"
                "            out[k] = \"***\"\n"
                "        else:\n"
                "            out[k] = v\n"
                "    return out\n"
            )
            files["app/config.py"] = cfg
    # bootstrap optional install hint
    boot = files.get("bootstrap.sh") or ""
    if opt_req and "requirements-optional" not in boot:
        boot = boot.replace(
            "pip install -q -r requirements.txt",
            "pip install -q -r requirements.txt\n"
            "if [ \"${INSTALL_OPTIONAL:-}\" = \"1\" ] && [ -f requirements-optional.txt ]; then\n"
            "  pip install -q -r requirements-optional.txt\n"
            "fi",
        )
        files["bootstrap.sh"] = boot
    if "README.md" not in files:
        files["README.md"] = "# Generated bot\n\nRun: chmod +x bootstrap.sh && ./bootstrap.sh\n"
    return files


def _repair_handler_imports(root: Path) -> list[str]:
    """Ensure main.py only imports symbols that handlers.py actually defines.

    Prevents ImportError on generated bots when emission drifts.
    """
    import re

    notes: list[str] = []
    main_p = root / "main.py"
    hand_p = root / "app" / "handlers.py"
    if not main_p.exists() or not hand_p.exists():
        return notes
    main = main_p.read_text(encoding="utf-8")
    handlers = hand_p.read_text(encoding="utf-8")
    defined = set(re.findall(r"(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", handlers))
    m = re.search(r"(from app\.handlers import )([^\n]+)", main)
    if not m:
        return notes
    names = [x.strip() for x in m.group(2).split(",") if x.strip()]
    kept = [n for n in names if n in defined]
    dropped = [n for n in names if n not in defined]
    if dropped:
        notes.append(f"dropped_undefined_handler_imports:{','.join(dropped[:20])}")
        # Always keep callback_router if defined
        new_import = m.group(1) + ", ".join(kept) if kept else m.group(1) + "start_handler"
        main2 = main[: m.start()] + new_import + main[m.end() :]
        # Also strip CommandHandler registrations that reference missing symbols
        for name in dropped:
            main2 = re.sub(
                rf"\n\s*app\.add_handler\(CommandHandler\([^)]*?,\s*{re.escape(name)}\s*\)\)",
                "",
                main2,
            )
        from telegram_bot_engine.services.safe_fs import safe_write_under_root
        safe_write_under_root(root, main_p, main2)

    # menu_shop requires market service
    if "async def menu_shop" in handlers:
        market = root / "app" / "services" / "market.py"
        if not market.exists():
            market.parent.mkdir(parents=True, exist_ok=True)
            try:
                from telegram_bot_engine.services.safe_fs import safe_write_under_root
                safe_write_under_root(root, market, _emit_market().rstrip() + "\n")
                notes.append("emitted_missing_market_service")
            except Exception:
                safe_write_under_root(root, market, 
                    '"""Auto-stub market service (generated)."""\n'
                    "def catalog(*a, **k):\n    return 'shop unavailable'\n",
                    encoding="utf-8",
                )
                notes.append("stubbed_missing_market_service")
    return notes



def _ensure_referenced_service_stubs(root: Path, files_written: list[str]) -> list[str]:
    """If any generated module imports a missing service, write a safe implementation."""
    import re
    from telegram_bot_engine.services.safe_fs import safe_write_under_root, safe_ident, UnsafePathError
    notes: list[str] = []
    root = Path(root)
    src_blob = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        try:
            src_blob.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    src = "\n".join(src_blob)
    needed = set(re.findall(r"from app\.services import (\w+)", src))
    needed |= set(re.findall(r"from app\.services\.(\w+) import", src))
    services_dir = root / "app" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)

    def _write(name: str, content: str, tag: str) -> None:
        from telegram_bot_engine.services.safe_fs import safe_ident, safe_write_text, UnsafePathError
        try:
            ident = safe_ident(name)
        except UnsafePathError:
            notes.append(f"skipped_bad_service_name:{name[:40]}")
            return
        rel = f"app/services/{ident}.py"
        target = root / rel
        if target.is_file():
            return
        try:
            safe_write_text(root, rel, content.rstrip() + "\n")
        except UnsafePathError as exc:
            notes.append(f"stub_write_rejected:{ident}:{exc}")
            return
        files_written.append(str(root / rel))
        notes.append(f"{tag}:{ident}")

    for name in sorted(needed):
        if name in {"i18n"}:
            continue
        target = services_dir / f"{name}.py"
        if target.is_file():
            continue
        # Root reliability: never emit dead stubs — working lean services only
        try:
            if name == "generic":
                content = _emit_lean_generic_service()
            else:
                content = _emit_lean_named_service(name)
        except Exception:
            content = _emit_lean_named_service(name)
        _write(name, content, "lean_service")

    if "app.flow_engine" in src or "from app.flow_engine" in src:
        fe = root / "app" / "flow_engine.py"
        if not fe.is_file():
            safe_write_under_root(root, fe, 
                '''"""Minimal flow engine stub — multi-step flows not enabled for this bot."""
from __future__ import annotations
from typing import Any

def active_flow(context: Any) -> bool:
    return bool(getattr(context, "user_data", {}) and context.user_data.get("flow"))

async def handle_text(update: Any, context: Any) -> bool:
    return False

async def handle_photo(update: Any, context: Any) -> bool:
    return False

async def handle_callback(update: Any, context: Any) -> bool:
    return False

def start_flow(*args: Any, **kwargs: Any) -> None:
    return None

def clear_flow(context: Any) -> None:
    if getattr(context, "user_data", None) is not None:
        context.user_data.pop("flow", None)
'''.rstrip()
                + "\n",
                encoding="utf-8",
            )
            files_written.append(str(fe))
            notes.append("stub_minimal:flow_engine")
    return notes



def write_project(spec: BotSpec, out_dir: str | Path) -> list[str]:
    import shutil
    from telegram_bot_engine.services.safe_fs import (
        UnsafePathError,
        enforce_under_output_dir,
    )
    # Foundation: never wipe/write outside OUTPUT_DIR
    try:
        root = enforce_under_output_dir(Path(out_dir))
    except UnsafePathError as exc:
        raise ValueError(f"write_project_root_rejected:{exc}") from exc
    if root.exists():
        for child in list(root.iterdir()):
            # only delete direct children that still resolve under root
            try:
                child.resolve().relative_to(root)
            except (ValueError, OSError):
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_file() or child.is_symlink():
                try:
                    child.unlink()
                except OSError:
                    pass
    root.mkdir(parents=True, exist_ok=True)
    files = generate_files(spec)
    feat_services = _feature_services(spec)
    try:
        plan_svcs = set(plan_from_spec(spec).services)
    except Exception:
        plan_svcs = set()
    svc_set = feat_services | plan_svcs
    # Never ship fat runtimes unless the selected services truly need them
    feat_keys = {getattr(f, "feature", "") for f in (spec.features or [])}
    needs_fat_market = bool(svc_set & _MARKET_SERVICES)
    needs_fat_generic = bool(svc_set & {"translate", "ocr", "scheduler"})
    needs_fat_flow = bool(svc_set & _FLOW_HINTS)
    needs_fat_tickets = bool(svc_set & {"tickets", "support"})
    if not needs_fat_market:
        files.pop("app/services/market.py", None)
    if not needs_fat_generic:
        files.pop("app/services/generic.py", None)
        files.pop("app/services/generic_runtime.json", None)
        # Always ship a WORKING lean generic (never dead __getattr__ stub)
        files["app/services/generic.py"] = _emit_lean_generic_service()

    # Root fix: reminders must never be a stub when remind_* is selected.
    # Emit a lean dedicated service (not fat generic_runtime).
    needs_reminders = bool(
        "reminders" in svc_set
        or "scheduler" in svc_set
        or any(str(k).startswith("remind_") for k in feat_keys)
    )
    if needs_reminders:
        files["app/services/reminders.py"] = _emit_reminders_service()

    needs_booking = bool(
        "booking" in svc_set
        or any(str(k).startswith("book_") for k in feat_keys)
    )
    needs_clinic = bool(
        "clinic" in svc_set
        or any(str(k).startswith("clinic_") for k in feat_keys)
    )
    if needs_booking:
        files["app/services/booking.py"] = _emit_booking_service()
    if needs_clinic:
        files["app/services/clinic.py"] = _emit_clinic_service()
    if not needs_fat_flow:
        files.pop("app/flow_engine.py", None)
    # Handlers may still import flow_engine for optional multi-step paths —
    # always keep a minimal working module so import validation never fails.
    handlers_src = files.get("app/handlers.py") or ""
    if ("app.flow_engine" in handlers_src or "from app.flow_engine" in handlers_src) and "app/flow_engine.py" not in files:
        files["app/flow_engine.py"] = (
            '"""Minimal flow engine — multi-step flows not enabled for this bot."""\n'
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n\n"
            "def active_flow(context: Any) -> bool:\n"
            '    return bool(getattr(context, "user_data", {}) and context.user_data.get("flow"))\n\n\n'
            "async def handle_text(update: Any, context: Any) -> bool:\n"
            "    return False\n\n\n"
            "async def handle_photo(update: Any, context: Any) -> bool:\n"
            "    return False\n\n\n"
            "async def handle_callback(update: Any, context: Any) -> bool:\n"
            "    return False\n\n\n"
            "def start_flow(*args: Any, **kwargs: Any) -> None:\n"
            "    return None\n\n\n"
            "def clear_flow(context: Any) -> None:\n"
            "    if getattr(context, \"user_data\", None) is not None:\n"
            '        context.user_data.pop("flow", None)\n'
        )
    if not needs_fat_tickets:
        files.pop("app/services/tickets.py", None)
    if not (svc_set & {"utils", "extras", "clinic", "jobs", "edu", "events", "restaurant",
                        "auction", "delivery", "crm", "booking", "community", "hr",
                        "marketplace", "fitness", "realestate", "shop", "cart", "wallet"}):
        files.pop("app/services/extras.py", None)
    written: list[str] = []
    from telegram_bot_engine.services.safe_fs import UnsafePathError, safe_write_text
    for rel, content in files.items():
        try:
            path = safe_write_text(root, str(rel), content.rstrip() + "\n")
        except UnsafePathError as exc:
            raise ValueError(f"generated_path_rejected:{rel}:{exc}") from exc
        written.append(str(path))
    try:
        _repair_handler_imports(root)
    except Exception:
        pass
    try:
        _ensure_referenced_service_stubs(root, written)
    except Exception:
        pass
    # Hard guard: never leave accidental fat packs on non-commerce bots
    from telegram_bot_engine.services.safe_fs import safe_write_under_root
    try:
        _MIN = (
            '"""Minimal import-safe stub."""\n'
            "from __future__ import annotations\n"
            "from typing import Any\n\n"
            "def __getattr__(item: str) -> Any:\n"
            "    def _missing(*args: Any, **kwargs: Any) -> str:\n"
            "        return f\"{item} is not available in this bot build\"\n"
            "    return _missing\n"
        )
        # Always clamp fat generic unless translate/ocr/scheduler/generic/utils selected
        g = root / "app" / "services" / "generic.py"
        if g.is_file() and g.stat().st_size > 4000 and not needs_fat_generic:
            safe_write_under_root(root, g, _MIN)
        gj = root / "app" / "services" / "generic_runtime.json"
        if gj.is_file() and not needs_fat_generic:
            try:
                gj.unlink()
            except OSError:
                pass
        # If handlers do not reference generic at all, delete stubs too
        handlers_src = ""
        hp = root / "app" / "handlers.py"
        if hp.is_file():
            handlers_src = hp.read_text(encoding="utf-8")
        if g.is_file() and "generic" not in handlers_src and not needs_fat_generic:
            try:
                g.unlink()
            except OSError:
                pass
        if not needs_fat_market:
            m = root / "app" / "services" / "market.py"
            if m.is_file() and m.stat().st_size > 4000:
                safe_write_under_root(root, m, _MIN)
        if not needs_fat_flow:
            fe = root / "app" / "flow_engine.py"
            if fe.is_file() and fe.stat().st_size > 4000:
                safe_write_under_root(root, fe, 
                    '''"""Minimal flow engine stub."""
from __future__ import annotations
from typing import Any

def active_flow(context: Any) -> bool:
    return False

async def handle_text(update: Any, context: Any) -> bool:
    return False

async def handle_photo(update: Any, context: Any) -> bool:
    return False

async def handle_callback(update: Any, context: Any) -> bool:
    return False

def start_flow(*args: Any, **kwargs: Any) -> None:
    return None

def clear_flow(context: Any) -> None:
    return None
''',
                    encoding="utf-8",
                )
    except Exception:
        pass
    return written


__all__ = ["generate_files", "write_project"]
