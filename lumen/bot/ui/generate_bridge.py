"""Run real generation from UI confirm (same engine path as message_router)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen_bot.ui")


async def run_guided_generation(
    *,
    message,
    context,
    user,
    gen_request: str,
    status_msg,
) -> Any:
    """Invoke run_generation + deliver_generation_result — no parallel engine."""
    from lumen.bot.config import OUTPUT_DIR
    from lumen.bot.sanitize import user_facing_generation_error
    from lumen.bot.helpers import run_generation, safe_edit_text
    from lumen.bot.progress_tracker import run_with_heartbeat

    gen_request = (gen_request or "").strip()
    if not gen_request:
        await safe_edit_text(status_msg, "لا يوجد وصف للتوليد.")
        return None

    if context.user_data is not None:
        context.user_data["engine_direct_request"] = gen_request
        context.user_data["force_generate_once"] = True
        context.user_data["skip_clarify_once"] = True

    work_dir: Path | None = None
    try:
        out_root = Path(OUTPUT_DIR)
        out_root.mkdir(parents=True, exist_ok=True)
        from lumen.engine.services.user_sandbox import get_user_sandbox

        uid = int(user.id) if user else 0
        work_dir = get_user_sandbox(uid, out_root).new_project_dir(label="gen")
    except Exception:
        logger.exception("sandbox workdir failed")
        try:
            from lumen.engine.services.user_sandbox import allocate_fallback_workdir

            work_dir = allocate_fallback_workdir(int(user.id) if user else 0)
        except Exception:
            logger.exception("fallback workdir failed")
            await safe_edit_text(status_msg, user_facing_generation_error(code="sandbox_unavailable"))
            try:
                from lumen.bot.ui.emit_context import emit_context_event
                await emit_context_event(
                    message=message, context=context, user=user,
                    kind="sandbox_unavailable",
                    detail=user_facing_generation_error(code="sandbox_unavailable"),
                )
            except Exception:
                pass
            return None

    preferred_keys = None
    try:
        result = await run_with_heartbeat(
            run_generation,
            gen_request,
            work_dir,
            int(user.id) if user else 0,
            status_msg=status_msg,
            preferred_keys=preferred_keys,
        )
    except Exception as exc:
        logger.exception("guided generation failed")
        await safe_edit_text(status_msg, user_facing_generation_error(exc))
        try:
            from lumen.bot.ui.emit_context import emit_context_event
            await emit_context_event(
                message=message, context=context, user=user,
                kind="generation_failed",
                detail=user_facing_generation_error(exc)[:400],
            )
        except Exception:
            pass
        return None

    if result is None:
        await safe_edit_text(status_msg, "فشل التوليد (نتيجة فارغة).")
        return None

    success = bool(getattr(result, "success", False))
    project_path = getattr(result, "project_path", None)
    if not success or not project_path:
        # Surface real engine reason (single edited message — no extra spam)
        code = "generation_failed"
        try:
            _errs = list(getattr(result, "errors", None) or [])
            if _errs:
                code = str(_errs[0])[:80]
        except Exception:
            pass
        try:
            errs = list(getattr(result, "errors", None) or [])
            if errs:
                raw = str(errs[0])[:120]
                code = raw.split(":")[0].strip() or code
                logger.warning("generation failed errors=%s meta=%s", errs[:5], getattr(result, "metadata", None))
        except Exception:
            pass
        await safe_edit_text(status_msg, user_facing_generation_error(code=code))
        return result

    try:
        from lumen.platform.plan_gate import apply_post_generation

        apply_post_generation(str(project_path), user_id=int(user.id) if user else 0)
    except Exception:
        logger.exception("post-generation plan hooks failed")

    try:
        from lumen.bot.generation_flow import deliver_generation_result

        await deliver_generation_result(
            message=message,
            status_msg=status_msg,
            context=context,
            user=user,
            request=gen_request,
            result=result,
        )
    except Exception:
        logger.exception("deliver_generation_result failed")
        await safe_edit_text(status_msg, f"تم التوليد. المسار: {project_path}")

    return result
