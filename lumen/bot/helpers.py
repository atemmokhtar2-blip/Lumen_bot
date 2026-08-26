"""Pure helper utilities for the Telegram bot interface."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from .config import ALLOWED_USER_IDS, ALLOW_ALL_USERS, logger
from .resource_limits import run_with_engine_timeout, EngineTimeoutError, clamp_spec_request


def is_allowed(user_id: int | None) -> bool:
    """Telegram bot access: public by default.

    - Default OPEN (ALLOW_ALL_USERS effective True).
    - LOCK_BOT_TO_ALLOWLIST=1 + ALLOWED_USER_IDS → allowlist only.
    - ALLOW_ALL_USERS=0 → closed.
    """
    if user_id is None:
        return False
    from .config import LOCK_BOT_TO_ALLOWLIST

    if LOCK_BOT_TO_ALLOWLIST and ALLOWED_USER_IDS:
        return user_id in ALLOWED_USER_IDS
    if ALLOW_ALL_USERS:
        return True
    if ALLOWED_USER_IDS:
        return user_id in ALLOWED_USER_IDS
    return False


def chat_route(text: str):
    """Single entry: natural language → capability (chat never writes code)."""
    try:
        from lumen.engine.services.chat_router import route_message
        return route_message(text or "")
    except Exception:
        return None


def detect_host_intent(text: str) -> str:
    """Return host action via ChatRouter."""
    r = chat_route(text)
    if r is None or not getattr(r, "ok", False):
        t = (text or "").strip().lower()
        if any(k in t for k in ("استضف", "استضافة", "host")):
            return "start"
        return "none"
    return {
        "host_start": "start",
        "host_stop": "stop",
        "host_status": "status",
        "host_diagnose": "diagnose",
    }.get(r.capability_id, "none")


def normalize_bot_token(text: str) -> str:
    """Collapse whitespace/newlines so pasted tokens still match."""
    return re.sub(r"\s+", "", (text or "").strip())


def looks_like_bot_token(text: str) -> bool:
    return bool(re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", normalize_bot_token(text)))


def escape_md(text: object) -> str:
    """Escape Telegram legacy Markdown special characters in dynamic text."""
    s = str(text) if text is not None else ""
    for ch in ("\\", "`", "*", "_", "[", "]", "(", ")"):
        s = s.replace(ch, f"\\{ch}")
    return s


async def safe_edit_text(message, text: str, *, use_markdown: bool = True) -> None:
    """edit_text with Markdown; fall back to plain text if Telegram rejects entities."""
    if use_markdown:
        try:
            from telegram.constants import ParseMode
            await message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            err = str(e).lower()
            if "can't parse entities" in err or "parse entities" in err:
                logger.warning("Markdown parse failed, retrying as plain text: %s", e)
            else:
                raise
    plain = (
        text.replace("\\", "")
        .replace("*", "")
        .replace("`", "")
        .replace("_", "")
    )
    await message.edit_text(plain)


def make_zip_from_path(project_path: str | Path) -> Path | None:
    """Create a clean, safe ZIP containing only deliverable project files."""
    project_path = Path(project_path).resolve()
    if not project_path.is_dir():
        return None

    zip_path = project_path.parent / f"{project_path.name}.zip"
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("zip parent mkdir failed")
        return None
    excluded_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
    excluded_names = {".env", ".env.local", ".env.production", "secrets.json"}
    tmp_zip = zip_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith(".")]
                for name in files:
                    full = (Path(root) / name).resolve()
                    if name in excluded_names or name.endswith((".pyc", ".pyo", ".log")):
                        continue
                    if full == zip_path or not full.is_file():
                        continue
                    try:
                        arc = full.relative_to(project_path)
                    except ValueError:
                        logger.warning("Skipping path outside project: %s", full)
                        continue
                    zf.write(full, arc.as_posix())
        os.replace(tmp_zip, zip_path)
        return zip_path
    except Exception as e:
        try:
            tmp_zip.unlink(missing_ok=True)
        except Exception:
            pass
        logger.exception("Failed to create zip: %s", e)
        return None


def split_file_for_telegram(path: str | Path, max_mb: float = 45.0) -> list[Path]:
    """Return one file or deterministic numbered parts below Telegram's upload limit."""
    source = Path(path).resolve()
    if not source.is_file():
        return []
    limit = max(1, int(max_mb * 1024 * 1024))
    if source.stat().st_size <= limit:
        return [source]
    parts: list[Path] = []
    try:
        with source.open("rb") as src:
            index = 1
            while True:
                chunk = src.read(limit)
                if not chunk:
                    break
                part = source.with_name(f"{source.name}.part{index:03d}")
                part.write_bytes(chunk)
                parts.append(part)
                index += 1
        return parts
    except Exception:
        for part in parts:
            part.unlink(missing_ok=True)
        logger.exception("Failed to split large delivery file: %s", source)
        return []


def run_generation(request: str, work_dir: Path, user_id: int = 0, preferred_keys=None):
    """Synchronous generation — Cline SDK only.

    Order:
      1) multi-agent orchestrator when enabled
      2) Cline via run_generation_with_bridge / execute_ir
    """
    request = clamp_spec_request(request or "")
    _bp_tenant = f"tg:{int(user_id or 0)}"
    _bp_acquired = False
    try:
        from lumen.platform.queue_backpressure import acquire_slot, release_slot
        ok_bp, reason_bp = acquire_slot(_bp_tenant)
        if not ok_bp:
            from lumen.engine.core.result import GenerationResult
            return GenerationResult(
                success=False,
                errors=[f"backpressure:{reason_bp}"],
                metadata={"backpressure": True, "reason": reason_bp},
            )
        _bp_acquired = True
    except Exception as _bp_exc:
        import os as _os
        if (_os.getenv("ENVIRONMENT") or "").strip().lower() in {"production", "prod", "staging"}:
            from lumen.engine.core.result import GenerationResult
            return GenerationResult(
                success=False,
                errors=[f"backpressure_error:{type(_bp_exc).__name__}"],
                metadata={"backpressure": True},
            )
        release_slot = None  # type: ignore

    try:

        # Hard LLM budget before any model/orchestrator spend
        try:
            from lumen.engine.services.llm_budget_gate import gate_llm_call
            ok, reason = gate_llm_call(
                request or "",
                {"user_id": int(user_id or 0)},
                response_reserve=4096,
            )
            if not ok:
                from lumen.engine.core.result import GenerationResult
                return GenerationResult(
                    success=False,
                    errors=[f"llm_budget_blocked:{reason}"],
                    metadata={"budget_blocked": True, "reason": reason},
                )
        except Exception as _bg_exc:
            import os as _os
            if (_os.getenv("ENVIRONMENT") or "").strip().lower() not in {"dev", "development", "local", "test"}:
                logger.exception("generation llm budget gate fail-closed")
                from lumen.engine.core.result import GenerationResult
                return GenerationResult(
                    success=False,
                    errors=[f"llm_budget_gate_error:{type(_bg_exc).__name__}"],
                    metadata={"budget_blocked": True},
                )
            logger.exception("generation llm budget gate failed (dev)")
        # Forced full AI path (manual experiment only)
        try:
            from lumen.engine.services.groq_codegen import (
                groq_codegen_enabled,
                generate_bot_via_groq,
            )
            if groq_codegen_enabled():
                logger.info("GROQ_CODEGEN_ENABLED=1 — full Groq codegen (manual)")
                return generate_bot_via_groq(
                    request,
                    work_dir,
                    user_id=int(user_id or 0),
                )
        except Exception:
            logger.exception("Groq codegen forced path failed; continuing with engine")

        # Multi-agent Phase A orchestrator (blackboard). Disable with MULTI_AGENT_ORCHESTRATOR=0
        try:
            from lumen.engine.services.multi_agent import (
                orchestrate_generate,
                orchestrator_enabled,
            )
            if orchestrator_enabled():
                logger.info("multi_agent orchestrator A–E — generate path")
                return orchestrate_generate(
                    request,
                    work_dir,
                    user_id=int(user_id or 0),
                    preferred_keys=preferred_keys if isinstance(preferred_keys, list) else None,
                )
        except Exception:
            logger.exception(
                "multi_agent orchestrator failed — verified template fallback (no bare engine loop)"
            )
            try:
                try:
                    from lumen.engine.services.multi_agent.production_policy import allow_template_fallback
                    if not allow_template_fallback():
                        raise RuntimeError("template_fallback_forbidden")
                except RuntimeError:
                    raise
                except Exception:
                    pass
                from lumen.engine.services.multi_agent.fallback_template import (
                    build_verified_bot,
                )
                fb = build_verified_bot(
                    request or "",
                    work_dir=work_dir,
                    user_id=int(user_id or 0),
                )
                if fb.ok and fb.generation_result is not None:
                    return fb.generation_result
                if fb.ok and fb.project_path:
                    from lumen.engine.core.result import GenerationResult
                    return GenerationResult(
                        success=True,
                        project_path=fb.project_path,
                        errors=[],
                        warnings=list(fb.warnings or []) + ["verified_template_emergency"],
                        metadata={"engine": "verified_template_fallback", "preset": fb.preset},
                    )
            except Exception:
                logger.exception("verified template emergency fallback failed")

        # Cline via bridge/IR.
        try:
            if (preferred_keys is not None) and isinstance(preferred_keys, dict):
                preferred_keys = preferred_keys.get("preferred_keys")  # type: ignore
        except Exception:
            pass

        logger.info("run_generation → Cline path")
        return run_generation_with_bridge(
            request,
            work_dir,
            user_id=int(user_id or 0),
            preferred_keys=preferred_keys if isinstance(preferred_keys, list) else None,
        )


    finally:
        if _bp_acquired:
            try:
                from lumen.platform.queue_backpressure import release_slot as _rs
                _rs(_bp_tenant)
            except Exception:
                pass


def run_generation_with_bridge(
    request: str,
    work_dir: Path,
    user_id: int = 0,
    translation: dict | None = None,
):
    """Analyze → BuildIR → engine_router (Cline SDK only).

    Translation is optional input to the bridge, not a required independent layer.
    Cline is the sole engine (CLINE_ENABLED defaults on).
    """
    from lumen.engine.services.engine_groq_bridge import analyze_and_prepare
    from lumen.engine.services.engine_router import build_ir_from_package, execute_ir

    request = clamp_spec_request(request or "")

    def _bridge_exec():
        package = analyze_and_prepare(request, translation)
        ir = build_ir_from_package(package, user_id=int(user_id or 0))
        logger.info(
            "IR mode=%s matched=%s gap=%s conf=%.2f",
            ir.engine_mode.value,
            ir.capabilities_matched,
            ir.capabilities_gap,
            ir.confidence,
        )
        result = execute_ir(ir, work_dir, user_id=int(user_id or 0))
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["bridge"] = package
            meta["ir"] = ir.to_dict()
            result.metadata = meta
        except Exception:
            pass
        return result

    try:
        return run_with_engine_timeout(_bridge_exec)
    except EngineTimeoutError as exc:
        from lumen.engine.core.result import GenerationResult
        logger.warning("engine timeout user=%s: %s", user_id, exc)
        return GenerationResult(
            success=False,
            errors=[f"engine_timeout:{exc}"],
            metadata={"timeout": True},
        )


async def safe_reply_text(message, text: str, *, use_markdown: bool = False) -> None:
    """reply_text that never fails silently on Markdown parse errors."""
    try:
        if use_markdown:
            from telegram.constants import ParseMode
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(text)
        return
    except Exception:
        try:
            await message.reply_text(str(text)[:4000])
        except Exception:
            from .config import logger
            logger.exception("safe_reply_text failed")
