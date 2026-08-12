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


def generate_files(spec: BotSpec) -> dict[str, str]:
    plan = plan_from_spec(spec)
    services = list(plan.services)
    files: dict[str, str] = {
        "app/__init__.py": "",
        "app/config.py": _emit_config(),
        "app/db.py": _emit_db(spec),
        "app/models.py": _emit_models(spec),
        "app/keyboards.py": _emit_keyboards(spec),
        "app/handlers.py": _emit_handlers(spec),
        "main.py": _emit_main(spec),
        "requirements.txt": "python-telegram-bot==21.6\npython-dotenv>=1.0.0\n",
        ".env.example": "TELEGRAM_BOT_TOKEN=\nADMIN_IDS=\n",
        "README.md": f"# {spec.bot.name}\n\nZero-AI generated Telegram bot.\n\n1. cp .env.example .env\n2. Set TELEGRAM_BOT_TOKEN\n3. pip install -r requirements.txt\n4. python main.py\n",
    }
    files["app/services/__init__.py"] = ""
    # Editable runtime data ships beside generic.py so generated projects are self-contained.
    files["app/services/generic_runtime.json"] = _emit_generic_runtime_data()
    # Runtime contract: handlers, routers, and service templates share these
    # modules across capability branches. Emitting them conditionally caused
    # real generated projects to fail the import gate (missing flow/market/db).
    svc_set = set(services)
    files["app/services/market.py"] = _emit_market()
    files["app/flow_engine.py"] = _emit_flow_engine()
    files["app/services/tickets.py"] = _emit_tickets()
    files["app/services/generic.py"] = _emit_generic_runtime()
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
    need_flow = bool(
        {
            "shop", "payments", "subscriptions", "points", "contests", "cart",
            "growth", "wallet", "i18n", "creator", "tickets", "tasks", "notes",
            "support",
        }
        & svc_set
    )
    if {
        "shop", "payments", "subscriptions", "points", "contests", "cart",
        "growth", "wallet", "i18n", "creator",
    } & svc_set:
        need_flow = True
    if need_flow:
        # Shared runtime files were emitted above; keep this branch only for
        # documenting the dependency contract and future optional expansion.
        files.setdefault("app/services/tickets.py", _emit_tickets())
        files.setdefault("app/services/market.py", _emit_market())
    if spec.storage.type == "sqlite" or len(spec.features) > 2 or (
        {"translate", "ocr", "scheduler", "generic", "utils"} & svc_set
    ):
        files["app/services/generic.py"] = _emit_generic_runtime()
    files.setdefault("bootstrap.sh", _emit_bootstrap_sh())

    # Phase 11: optional production backends for translate / OCR / schedule
    req_lines = ["python-telegram-bot==21.6", "python-dotenv>=1.0.0"]
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
        main_p.write_text(main2, encoding="utf-8")

    # menu_shop requires market service
    if "async def menu_shop" in handlers:
        market = root / "app" / "services" / "market.py"
        if not market.exists():
            market.parent.mkdir(parents=True, exist_ok=True)
            try:
                market.write_text(_emit_market().rstrip() + "\n", encoding="utf-8")
                notes.append("emitted_missing_market_service")
            except Exception:
                market.write_text(
                    '"""Auto-stub market service (generated)."""\n'
                    "def catalog(*a, **k):\n    return 'shop unavailable'\n",
                    encoding="utf-8",
                )
                notes.append("stubbed_missing_market_service")
    return notes


def write_project(spec: BotSpec, out_dir: str | Path) -> list[str]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, content in generate_files(spec).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        written.append(str(path))
    try:
        _repair_handler_imports(root)
    except Exception:
        pass
    return written


__all__ = ["generate_files", "write_project"]
