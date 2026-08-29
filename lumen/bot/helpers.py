"""Pure helper utilities for the Telegram bot interface."""

from __future__ import annotations

import os
import re
import stat
import zipfile
from pathlib import Path

from .config import ALLOWED_USER_IDS, ALLOW_ALL_USERS, logger
from .resource_limits import run_with_engine_timeout, EngineTimeoutError, clamp_spec_request


def is_allowed(user_id: int | None) -> bool:
    """Telegram bot access — secure by default (closed).

    Decision tree (single, no duplication):
      1. None user_id            → deny
      2. ALLOW_ALL_USERS=True    → allow everyone (explicit public opt-in)
      3. ALLOWED_USER_IDS set    → allow only listed IDs
      4. Otherwise               → deny (prevents anonymous API-cost drain)

    LOCK_BOT_TO_ALLOWLIST is a hardening flag that is redundant with
    ALLOWED_USER_IDS being set (case 3 already restricts). It exists for
    operator intent clarity but does not add a separate branch.
    """
    if user_id is None:
        return False
    from .config import LOCK_BOT_TO_ALLOWLIST

    # Explicit public mode — highest priority, explicit opt-in only.
    if ALLOW_ALL_USERS:
        return True

    # Restricted mode — allowlist governs access.
    if ALLOWED_USER_IDS:
        # LOCK_BOT_TO_ALLOWLIST is an explicit hardening signal; even without
        # it, having ALLOWED_USER_IDS set already means restricted mode.
        return user_id in ALLOWED_USER_IDS

    # Secure default: closed. No allowlist and no explicit public mode.
    # LOCK_BOT_TO_ALLOWLIST without any IDs means "deny everyone" (safe).
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
    try:
        from lumen.engine.services.safe_zip import write_project_zip

        return write_project_zip(project_path)
    except Exception as e:
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
    # Fail-closed security scan before any engine work
    try:
        from lumen.engine.pipeline.prompt_guard import scan_user_input
        _gr = scan_user_input(request)
        if not _gr.ok:
            from lumen.engine.core.result import GenerationResult
            return GenerationResult(
                success=False,
                errors=["guardrails:" + ",".join(_gr.reasons)[:300]],
                metadata={"guardrails": {"ok": False, "reasons": list(_gr.reasons), "backend": _gr.backend}},
            )
        if _gr.sanitized:
            request = clamp_spec_request(_gr.sanitized)
    except Exception as _gexc:
        from lumen.engine.core.result import GenerationResult
        return GenerationResult(
            success=False,
            errors=[f"guardrails_error:{type(_gexc).__name__}"],
            metadata={"guardrails": {"ok": False, "error": type(_gexc).__name__}},
        )
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
        # Multi-agent Phase A orchestrator (blackboard). Disable with MULTI_AGENT_ORCHESTRATOR=0
        # If orchestrator cannot run (missing langgraph, etc.) → fall through to Cline.
        try:
            from lumen.engine.services.multi_agent import (
                orchestrate_generate,
                orchestrator_enabled,
            )
            if orchestrator_enabled():
                logger.info("multi_agent orchestrator A–E — generate path")
                _orch_res = orchestrate_generate(
                    request,
                    work_dir,
                    user_id=int(user_id or 0),
                    preferred_keys=preferred_keys if isinstance(preferred_keys, list) else None,
                )
                if getattr(_orch_res, "success", False):
                    return _orch_res
                _orch_errs = list(getattr(_orch_res, "errors", None) or [])
                _orch_join = " ".join(str(x) for x in _orch_errs).lower()
                _fallbackable = any(
                    k in _orch_join
                    for k in (
                        "langgraph_required",
                        "langchain",
                        "module",
                        "import",
                        "not installed",
                        "no_llm_provider",
                    )
                )
                if not _fallbackable:
                    return _orch_res
                logger.warning(
                    "multi_agent failed (%s) — falling through to Cline",
                    _orch_errs[:3],
                )
        except Exception as _orch_exc:
            logger.exception("multi_agent orchestrator exception — falling through to Cline")

        # Cline engine-direct fallback (no translator/bridge layer).
        try:
            if (preferred_keys is not None) and isinstance(preferred_keys, dict):
                preferred_keys = preferred_keys.get("preferred_keys")  # type: ignore
        except Exception:
            pass

        logger.info("run_generation → Cline engine-direct path")
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
    preferred_keys: list | None = None,
):
    """Engine-direct fallback: raw request → BuildIR → Cline (no translator/bridge layer).

    Multi-agent is preferred by run_generation. This path is only the Cline fallback.
    Engine reads its own LLM keys via model_router + key_pool.
    """
    from lumen.engine.services.engine_router import build_ir_from_package, execute_ir

    request = clamp_spec_request(request or "")

    def _engine_direct_exec():
        # Minimal package — engine owns understanding. No analyze_and_prepare.
        package: dict = {
            "original_text": request,
            "spec_request": request,
            "preferred_keys": list(preferred_keys or []),
            "capabilities_matched": [],
            "capabilities_gap": ["free_agent"],
            "needs_ai_codegen": True,
            "looks_custom": True,
            "confidence": 0.0,
            "engine_mode": "cline",
        }
        if isinstance(translation, dict) and translation:
            # Optional residual hints only; never required.
            if translation.get("spec_request"):
                package["spec_request"] = str(translation.get("spec_request") or request).strip()
            feats = translation.get("features_requested") or translation.get("preferred_keys")
            if isinstance(feats, list) and feats:
                package["preferred_keys"] = [str(x).strip() for x in feats if str(x).strip()]
        ir = build_ir_from_package(package, user_id=int(user_id or 0))
        logger.info(
            "engine-direct IR mode=%s matched=%s gap=%s conf=%.2f",
            ir.engine_mode.value,
            ir.capabilities_matched,
            ir.capabilities_gap,
            ir.confidence,
        )
        result = execute_ir(ir, work_dir, user_id=int(user_id or 0))
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["engine_direct"] = True
            meta["ir"] = ir.to_dict()
            result.metadata = meta
        except Exception:
            pass
        return result

    try:
        return run_with_engine_timeout(_engine_direct_exec)
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
