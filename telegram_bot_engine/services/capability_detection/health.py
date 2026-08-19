"""Phase 10 — Capability system health + post-generation smoke (hardened).

Deterministic. Offline-safe.
Env:
  CAPABILITY_SMOKE_STRICT=1  → smoke failures can fail the build (via caller)
  CAPABILITY_HEALTH_LOG=1    → persist last health JSON under OUTPUT_DIR
"""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    base = os.getenv("OUTPUT_DIR") or _cm_default_output_dir()
    p = Path(base) / "platform" / "health"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _persist_report(name: str, payload: dict[str, Any]) -> str | None:
    if os.getenv("CAPABILITY_HEALTH_LOG", "1").strip().lower() not in {"1", "true", "yes"}:
        return None
    try:
        path = _data_dir() / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception:
        return None


def capability_system_health() -> dict[str, Any]:
    """Import/load smoke for the Dynamic Tool Builder stack."""
    t0 = time.time()
    checks: list[dict[str, Any]] = []

    def _ok(name: str, detail: str = "", *, critical: bool = False) -> None:
        checks.append({"name": name, "ok": True, "detail": detail, "critical": critical})

    def _fail(name: str, detail: str, *, critical: bool = True) -> None:
        checks.append({"name": name, "ok": False, "detail": detail, "critical": critical})

    modules = [
        "telegram_bot_engine.services.capability_detection.engine",
        "telegram_bot_engine.services.capability_detection.synthesis",
        "telegram_bot_engine.services.capability_detection.web_research",
        "telegram_bot_engine.services.capability_detection.learning_loop",
        "telegram_bot_engine.services.capability_detection.pack_promotion",
        "telegram_bot_engine.services.capability_detection.pipeline_trace",
        "telegram_bot_engine.services.capability_detection.packs.loader",
        "telegram_bot_engine.services.capability_detection.packs.emit_contract",
    ]
    for mod in modules:
        try:
            __import__(mod)
            _ok(f"import:{mod.split('.')[-1]}")
        except Exception as exc:
            _fail(f"import:{mod.split('.')[-1]}", f"{type(exc).__name__}: {exc}")

    try:
        from .packs.loader import load_all_packs
        from ...spec_core.registry import get_capability
        from ...spec_core.builder import DEFAULT_COMMANDS

        info = load_all_packs()
        for key in (
            "scaffold_translate", "scaffold_ocr", "scaffold_schedule",
            "scaffold_voice", "scaffold_payment_info", "scaffold_faq_bot",
        ):
            cap = get_capability(key)
            if cap is None:
                _fail(f"scaffold:{key}", "missing from registry")
            else:
                cmd = DEFAULT_COMMANDS.get(key)
                _ok(f"scaffold:{key}", f"cmd=/{cmd} service={cap.service}.{cap.method}")
        _ok("packs_loaded", f"ids={info.get('loaded_pack_ids')}")
    except Exception as exc:
        _fail("packs", f"{type(exc).__name__}: {exc}")

    try:
        from .engine import detect_capabilities
        from .models import DetectionStatus

        r = detect_capabilities("بوت ترحيب للمجموعة")
        if r.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE) and r.matched:
            _ok("detect_welcome", f"status={r.status.value} n={len(r.matched)}")
        else:
            _fail("detect_welcome", f"status={r.status.value}")
        r2 = detect_capabilities("بوت يترجم الرسائل تلقائياً")
        keys = {m.key for m in r2.matched}
        if "scaffold_translate" in keys:
            _ok("detect_translate_scaffold", "covered")
        else:
            _fail("detect_translate_scaffold", f"keys={list(keys)[:8]}")
    except Exception as exc:
        _fail("detection", f"{type(exc).__name__}: {exc}")

    try:
        from .packs.emit_contract import assess_capability

        for svc, meth in (
            ("translate", "translate"),
            ("ocr", "ocr_hint"),
            ("scheduler", "schedule_note"),
            ("generic", "echo"),
        ):
            a = assess_capability("x", svc, meth)
            if a.safe:
                _ok(f"emit:{svc}.{meth}")
            else:
                _fail(f"emit:{svc}.{meth}", a.level)
    except Exception as exc:
        _fail("emit_contract", str(exc))

    try:
        from .pipeline_trace import pipeline_trace

        tr = pipeline_trace("بوت ترحيب", include_research=False)
        if tr.get("ok") and tr.get("fail_safe"):
            _ok("pipeline_trace", tr["fail_safe"].get("level", ""))
        else:
            _fail("pipeline_trace", "missing fail_safe")
    except Exception as exc:
        _fail("pipeline_trace", f"{type(exc).__name__}: {exc}")

    critical_failed = [c for c in checks if not c["ok"] and c.get("critical", True)]
    ok_all = len(critical_failed) == 0
    out = {
        "ok": ok_all,
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "critical_failed": len(critical_failed),
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
    out["log_path"] = _persist_report("system_health_last", out)
    return out


def _command_for_key(key: str) -> str:
    try:
        from ...spec_core.builder import DEFAULT_COMMANDS
        return str(DEFAULT_COMMANDS.get(key) or key.replace("_", "")[:32])
    except Exception:
        return key.replace("_", "")[:32]


def smoke_generated_project(
    project_path: str | Path,
    *,
    expected_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Static smoke checks on a Zero-AI generated bot project."""
    root = Path(project_path)
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def _ok(name: str, detail: str = "", *, critical: bool = False) -> None:
        checks.append({"name": name, "ok": True, "detail": detail, "critical": critical})

    def _fail(name: str, detail: str, *, critical: bool = True) -> None:
        checks.append({"name": name, "ok": False, "detail": detail, "critical": critical})
        errors.append(f"{name}: {detail}")

    if not root.is_dir():
        return {
            "ok": False,
            "errors": [f"missing_dir:{root}"],
            "checks": [],
            "critical_failed": 1,
        }

    required = [
        ("main.py", True),
        ("app/handlers.py", True),
        ("app/config.py", True),
        ("requirements.txt", True),
        (".env.example", False),
        ("README.md", False),
    ]
    for rel, critical in required:
        p = root / rel
        if p.is_file() and p.stat().st_size > 0:
            _ok(f"file:{rel}", f"bytes={p.stat().st_size}", critical=critical)
        else:
            _fail(f"file:{rel}", "missing_or_empty", critical=critical)

    handlers = root / "app" / "handlers.py"
    handler_src = ""
    if handlers.is_file():
        try:
            handler_src = handlers.read_text(encoding="utf-8")
            ast.parse(handler_src)
            _ok("handlers_syntax")
        except SyntaxError as exc:
            _fail("handlers_syntax", str(exc))

    main = root / "main.py"
    main_src = ""
    if main.is_file():
        try:
            main_src = main.read_text(encoding="utf-8")
            ast.parse(main_src)
            _ok("main_syntax")
        except SyntaxError as exc:
            _fail("main_syntax", str(exc))

    # requirements must mention telegram
    req = root / "requirements.txt"
    if req.is_file():
        rtxt = req.read_text(encoding="utf-8", errors="ignore").lower()
        if "python-telegram-bot" in rtxt or "telegram" in rtxt:
            _ok("requirements_telegram")
        else:
            _fail("requirements_telegram", "python-telegram-bot not pinned")

    expected = list(expected_keys or [])
    for key in expected:
        if key in {"start", "help"}:
            continue
        hname = f"handle_{key}".replace("-", "_")
        if handler_src and (hname in handler_src or f"handle_{key}" in handler_src or key in handler_src):
            _ok(f"handler:{key}")
        else:
            _fail(f"handler:{key}", f"missing {hname}")

        # CommandHandler registration in main
        cmd = _command_for_key(key)
        if main_src:
            # accept CommandHandler('cmd' or "cmd"
            pat = re.compile(
                rf"CommandHandler\(\s*['\"]({re.escape(cmd)}|{re.escape(key)})['\"]",
                re.I,
            )
            # A capability may intentionally expose one or more user-facing aliases
            # (e.g. lead_capture -> /register and /new_client). In that case the
            # capability id is not the Telegram command. Accept only a real
            # CommandHandler whose callback is the expected handler, never a bare
            # occurrence of the command string elsewhere in main.py.
            handler_pat = re.compile(
                rf"CommandHandler\(\s*['\"][^'\"]+['\"]\s*,\s*handle_{re.escape(key)}\b",
                re.I,
            )
            if pat.search(main_src) or handler_pat.search(main_src):
                _ok(f"command_registered:{cmd}")
            else:
                # non-critical if handler exists (alias path)
                _fail(
                    f"command_registered:{cmd}",
                    f"CommandHandler for {cmd}/{key} not found in main",
                    critical=False,
                )

    # Scaffold runtimes
    generic = root / "app" / "services" / "generic.py"
    needs_generic = any(
        k.startswith("scaffold_") or k.startswith("pack_learned_")
        for k in expected
    )
    if needs_generic:
        if generic.is_file():
            gsrc = generic.read_text(encoding="utf-8")
            try:
                ast.parse(gsrc)
                _ok("generic_syntax")
            except SyntaxError as exc:
                _fail("generic_syntax", str(exc))
            if "scaffold_translate" in expected:
                if "translate_text" in gsrc:
                    _ok("scaffold_translate_runtime")
                else:
                    _fail("scaffold_translate_runtime", "translate_text missing")
            if "scaffold_ocr" in expected:
                if "ocr_hint" in gsrc or "ocr_from_image" in gsrc:
                    _ok("scaffold_ocr_runtime")
                else:
                    _fail("scaffold_ocr_runtime", "ocr helpers missing")
                if "photo_router" in handler_src or "filters.PHOTO" in main_src:
                    _ok("ocr_photo_wiring")
                else:
                    _fail("ocr_photo_wiring", "photo_router not registered")
            if "scaffold_schedule" in expected:
                if "schedule_note" in gsrc:
                    _ok("scaffold_schedule_runtime")
                else:
                    _fail("scaffold_schedule_runtime", "schedule_note missing")
        else:
            _fail("generic.py", "missing for scaffold features")

    if main_src:
        if "Application" in main_src and "add_handler" in main_src:
            _ok("main_registers_handlers")
        else:
            _fail("main_registers_handlers", "no Application/add_handler")

    critical_failed = [c for c in checks if not c["ok"] and c.get("critical", True)]
    ok_all = len(critical_failed) == 0
    out = {
        "ok": ok_all,
        "project_path": str(root),
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "critical_failed": len(critical_failed),
        "errors": errors,
        "strict": os.getenv("CAPABILITY_SMOKE_STRICT", "").strip().lower() in {"1", "true", "yes"},
    }
    out["log_path"] = _persist_report("project_smoke_last", out)
    return out


def attach_generation_diagnostics(
    *,
    request: str,
    project_path: str | Path | None,
    preferred_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Bundle system health + optional project smoke + pipeline trace."""
    out: dict[str, Any] = {
        "system_health": capability_system_health(),
    }
    try:
        from .pipeline_trace import pipeline_trace
        out["pipeline"] = pipeline_trace(request or "", include_research=False)
    except Exception as exc:
        out["pipeline_error"] = str(exc)[:200]
    if project_path:
        out["project_smoke"] = smoke_generated_project(
            project_path, expected_keys=list(preferred_keys or [])
        )
    health_ok = bool(out["system_health"].get("ok"))
    smoke_ok = bool(out.get("project_smoke", {}).get("ok", True))
    out["ok"] = health_ok and smoke_ok
    # strict: caller may fail build when project_smoke has critical failures
    out["should_fail_build"] = bool(
        out.get("project_smoke", {}).get("strict")
        and (out.get("project_smoke", {}).get("critical_failed") or 0) > 0
    )
    out["log_path"] = _persist_report("diagnostics_last", {
        "ok": out["ok"],
        "should_fail_build": out["should_fail_build"],
        "request": (request or "")[:200],
        "project_path": str(project_path) if project_path else None,
    })
    return out


def health_summary_ar(health: dict[str, Any] | None = None) -> str:
    """Short Arabic summary for soft notes / ops."""
    h = health or capability_system_health()
    if h.get("ok"):
        return f"✅ صحة النظام: {h.get('passed')}/{h.get('passed', 0) + h.get('failed', 0)} فحص ناجح"
    fails = [c["name"] for c in h.get("checks", []) if not c.get("ok")]
    return "⚠️ صحة النظام: فشل " + "، ".join(fails[:6])


__all__ = [
    "capability_system_health",
    "smoke_generated_project",
    "attach_generation_diagnostics",
    "health_summary_ar",
]
