from __future__ import annotations

from pathlib import Path
from typing import Any

from ..coding_emit_foundation import _emit_config, _emit_db, _emit_models
from ..coding_emit_services import (
    _emit_reminders_service,
    _emit_booking_service,
    _emit_clinic_service,
    _emit_lean_generic_service,
    _emit_lean_named_service,
    _emit_content,
    _emit_extras,
    _emit_moderation,
    _emit_notes,
    _emit_security,
    _emit_tasks,
    _emit_tickets,
    _emit_welcome,
    _emit_pubg,
)
from ..templates_sentry import emit_sentry_setup
from ..coding_handlers import _emit_handlers, _emit_keyboards, _emit_main
from ..planning import plan_from_spec
from ..schema import BotSpec
from ..emitters.project_emitters import (
    _feature_services,
    _MARKET_SERVICES,
    _FLOW_HINTS,
    _GENERIC_HINTS,
    generate_files,
    _emit_bootstrap_sh,
    _emit_gitignore,
    _emit_readme,
    _emit_env_example,
    _emit_quality_tests,
    _emit_flow_engine,
    _emit_market,
    _emit_generic_runtime,
    _emit_generic_runtime_data,
    _emit_i18n_service,
)
from ..validators.ast_validators import _repair_handler_imports, _ensure_referenced_service_stubs






def write_project(spec: BotSpec, out_dir: str | Path) -> list[str]:
    import shutil
    from lumen.engine.services.safe_fs import (
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
                shutil.rmtree(child)  # fail loud — ghost dirs poison next generate
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
    needs_fat_market = bool(svc_set & _MARKET_SERVICES) or any(
        str(k).startswith(p)
        for k in feat_keys
        for p in ("shop_", "cart_", "wallet_", "mkt_", "coupon_", "order_", "product_", "wishlist_", "refund_")
    )
    needs_fat_generic = bool(svc_set & {"translate", "ocr", "scheduler"})
    needs_fat_flow = bool(svc_set & _FLOW_HINTS)
    needs_fat_tickets = bool(svc_set & {"tickets", "support"}) or any(
        str(k).startswith(p) for k in feat_keys for p in ("ticket_", "faq_")
    )
    needs_fat_tasks = bool(svc_set & {"tasks", "notes"}) or any(
        str(k).startswith(p) for k in feat_keys for p in ("task_", "note_")
    )
    needs_fat_booking = bool(svc_set & {"booking", "clinic"}) or any(
        str(k).startswith(p) for k in feat_keys for p in ("book_", "clinic_", "gym_")
    )
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

    needs_booking = bool(needs_fat_booking) or bool(
        "booking" in svc_set
        or any(str(k).startswith("book_") for k in feat_keys)
    )
    needs_clinic = bool(needs_fat_booking) or bool(
        "clinic" in svc_set
        or any(str(k).startswith("clinic_") for k in feat_keys)
    )
    if needs_fat_tasks:
        files["app/services/tasks.py"] = _emit_tasks()
        files["app/services/notes.py"] = _emit_notes()
    if needs_fat_tickets:
        files["app/services/tickets.py"] = _emit_tickets()
    needs_fat_mod = bool(svc_set & {"moderation", "admin"}) or any(
        str(k).startswith(p) for k in feat_keys
        for p in ("user_ban", "user_warn", "user_mute", "user_kick", "delete_message", "purge", "rules")
    ) or any(str(k) in {"user_ban","user_warn","user_mute","user_kick","delete_message","purge","rules"} for k in feat_keys)
    if needs_fat_mod:
        files["app/services/moderation.py"] = _emit_moderation()
    needs_fat_content = bool(svc_set & {"content", "welcome"}) or any(
        str(k).startswith(p) for k in feat_keys for p in ("welcome_", "faq_", "announce", "rules")
    )
    if needs_fat_content:
        files["app/services/content.py"] = _emit_content(spec)
        files["app/services/welcome.py"] = _emit_welcome()
    needs_fat_crm = bool(svc_set & {"crm"}) or any(
        str(k).startswith(p) for k in feat_keys for p in ("lead_", "followup_")
    )
    if needs_fat_crm:
        from pathlib import Path as _P
        _crm = _P(__file__).resolve().parents[1] / "runtime" / "crm_runtime.py"
        if _crm.is_file():
            files["app/services/crm.py"] = _crm.read_text(encoding="utf-8")
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

    needs_fat_security = bool(svc_set & {"security"}) or any(
        str(k).startswith(("sec_", "report_")) for k in feat_keys
    )
    if needs_fat_security:
        files["app/services/security.py"] = _emit_security()

    written: list[str] = []
    from lumen.engine.services.safe_fs import UnsafePathError, safe_write_text
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
    from lumen.engine.services.safe_fs import safe_write_under_root
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

