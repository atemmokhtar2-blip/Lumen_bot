"""Phase 10 — Capability system health + post-generation smoke checks.

Deterministic. No network required (offline-safe).
"""
from __future__ import annotations

import ast
import os
import time
from pathlib import Path
from typing import Any


def capability_system_health() -> dict[str, Any]:
    """Import/load smoke for the whole Dynamic Tool Builder stack."""
    t0 = time.time()
    checks: list[dict[str, Any]] = []

    def _ok(name: str, detail: str = "") -> None:
        checks.append({"name": name, "ok": True, "detail": detail})

    def _fail(name: str, detail: str) -> None:
        checks.append({"name": name, "ok": False, "detail": detail})

    # Module imports
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

    # Packs + scaffolds
    try:
        from .packs.loader import load_all_packs
        from ...spec_core.registry import get_capability
        from ...spec_core.builder import DEFAULT_COMMANDS

        info = load_all_packs()
        for key in ("scaffold_translate", "scaffold_ocr", "scaffold_schedule"):
            cap = get_capability(key)
            if cap is None:
                _fail(f"scaffold:{key}", "missing from registry")
            else:
                cmd = DEFAULT_COMMANDS.get(key)
                _ok(f"scaffold:{key}", f"cmd=/{cmd} service={cap.service}.{cap.method}")
        _ok("packs_loaded", f"ids={info.get('loaded_pack_ids')}")
    except Exception as exc:
        _fail("packs", f"{type(exc).__name__}: {exc}")

    # Detection sanity
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

    # Emit contract
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

    # Pipeline trace (no recursion)
    try:
        from .pipeline_trace import pipeline_trace

        tr = pipeline_trace("بوت ترحيب", include_research=False)
        if tr.get("ok") and tr.get("fail_safe"):
            _ok("pipeline_trace", tr["fail_safe"].get("level", ""))
        else:
            _fail("pipeline_trace", "missing fail_safe")
    except Exception as exc:
        _fail("pipeline_trace", f"{type(exc).__name__}: {exc}")

    ok_all = all(c["ok"] for c in checks)
    return {
        "ok": ok_all,
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


def smoke_generated_project(
    project_path: str | Path,
    *,
    expected_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Static smoke checks on a Zero-AI generated bot project."""
    root = Path(project_path)
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def _ok(name: str, detail: str = "") -> None:
        checks.append({"name": name, "ok": True, "detail": detail})

    def _fail(name: str, detail: str) -> None:
        checks.append({"name": name, "ok": False, "detail": detail})
        errors.append(f"{name}: {detail}")

    if not root.is_dir():
        return {"ok": False, "errors": [f"missing_dir:{root}"], "checks": []}

    required = [
        "main.py",
        "app/handlers.py",
        "app/config.py",
        "requirements.txt",
    ]
    for rel in required:
        p = root / rel
        if p.is_file() and p.stat().st_size > 0:
            _ok(f"file:{rel}", f"bytes={p.stat().st_size}")
        else:
            _fail(f"file:{rel}", "missing_or_empty")

    # Parse handlers for syntax
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

    # Expected capability handlers / commands
    for key in expected_keys or []:
        if key in {"start", "help"}:
            continue
        hname = f"handle_{key}".replace("-", "_")
        # command may be shortened
        if handler_src and (hname in handler_src or key in handler_src):
            _ok(f"handler:{key}")
        else:
            _fail(f"handler:{key}", f"missing {hname}")

    # Scaffold-specific markers
    generic = root / "app" / "services" / "generic.py"
    if any(k.startswith("scaffold_") or k in {
        "scaffold_translate", "scaffold_ocr", "scaffold_schedule"
    } for k in (expected_keys or [])):
        if generic.is_file():
            gsrc = generic.read_text(encoding="utf-8")
            try:
                ast.parse(gsrc)
                _ok("generic_syntax")
            except SyntaxError as exc:
                _fail("generic_syntax", str(exc))
            if "scaffold_translate" in (expected_keys or []) and "translate_text" not in gsrc:
                _fail("scaffold_translate_runtime", "translate_text missing")
            elif "scaffold_translate" in (expected_keys or []):
                _ok("scaffold_translate_runtime")
            if "scaffold_ocr" in (expected_keys or []):
                if "ocr_hint" in gsrc or "ocr_from_image" in gsrc:
                    _ok("scaffold_ocr_runtime")
                else:
                    _fail("scaffold_ocr_runtime", "ocr helpers missing")
                if "photo_router" not in handler_src and "filters.PHOTO" not in main_src:
                    _fail("ocr_photo_wiring", "photo_router not registered")
                else:
                    _ok("ocr_photo_wiring")
        else:
            _fail("generic.py", "missing for scaffold features")

    # main registers Application
    if main_src:
        if "Application" in main_src and "add_handler" in main_src:
            _ok("main_registers_handlers")
        else:
            _fail("main_registers_handlers", "no Application/add_handler")

    ok_all = all(c["ok"] for c in checks) if checks else False
    return {
        "ok": ok_all,
        "project_path": str(root),
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "errors": errors,
    }


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
    out["ok"] = bool(out["system_health"].get("ok")) and (
        out.get("project_smoke", {}).get("ok", True)
    )
    return out


__all__ = [
    "capability_system_health",
    "smoke_generated_project",
    "attach_generation_diagnostics",
]
