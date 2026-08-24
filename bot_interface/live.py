"""Live run and live deployment token handlers."""

from __future__ import annotations

import asyncio
import os
import time

from .config import logger, LIVE_RUN_SECONDS
from .helpers import escape_md, safe_edit_text


async def handle_live_run_token(message, context, token: str, pending: dict) -> None:
    """Validate + install + start bot; respond quickly (bot keeps running in background)."""
    status = await message.reply_text(
        "🔐 1/4 التحقق من التوكن..."
    )
    project_path = pending.get("project_path")
    entry = pending.get("entry_point") or ""
    run_seconds = float(
        pending.get("run_seconds")
        or LIVE_RUN_SECONDS
    )

    # Heartbeat while the blocking worker runs (install can take minutes)
    stop_hb = asyncio.Event()

    async def _heartbeat() -> None:
        phases = [
            "🔐 1/4 التحقق من التوكن...",
            "📦 2/4 تثبيت التبعيات (قد يستغرق دقيقة أو أكثر)...",
            "🔧 3/4 إصلاح تلقائي إن لزم...",
            "🚀 4/4 تشغيل البوت وفحص الإقلاع...",
        ]
        i = 0
        started = time.monotonic()
        while not stop_hb.is_set():
            elapsed = int(time.monotonic() - started)
            phase = phases[min(i, len(phases) - 1)]
            try:
                await status.edit_text(f"{phase}\n⏳ مرّ {elapsed}ث — لسه شغال، متقلقش.")
            except Exception:
                pass
            i = min(i + 1, len(phases) - 1)
            try:
                await asyncio.wait_for(stop_hb.wait(), timeout=12)
            except asyncio.TimeoutError:
                continue

    hb_task = asyncio.create_task(_heartbeat())

    def _run():
        from telegram_bot_engine.services.live_runner import run_bot_project
        return run_bot_project(
            project_path=project_path,
            bot_token=token,
            entry_hint=entry or None,
            run_seconds=run_seconds,
        )

    try:
        report = await asyncio.to_thread(_run)
    except Exception as e:
        logger.exception("Live run failed")
        stop_hb.set()
        try:
            await hb_task
        except Exception:
            pass
        from .sanitize import sanitize_error
        await status.edit_text(f"❌ فشل التشغيل الحي: {type(e).__name__}: {sanitize_error(str(e), max_len=200)}")
        context.user_data.pop("pending_run", None)
        return
    finally:
        token = ""  # noqa: F841
        stop_hb.set()
        try:
            await asyncio.wait_for(hb_task, timeout=2)
        except Exception:
            hb_task.cancel()

    context.user_data.pop("pending_run", None)
    text_out = report.to_user_text()
    if len(text_out) > 3500:
        text_out = text_out[:3500] + "\n…"
    await status.edit_text(text_out)


def _local_process_fallback_allowed() -> bool:
    """Host-process fallback permanently disabled (Docker or reject)."""
    return False


async def handle_live_deploy_token(message, context, token: str, pending: dict) -> None:
    """Deploy generated bot via LiveDeploymentEngine (Docker-first, fail-closed).

    Host-process LiveRunner is never used when isolation requires Docker
    (multi-tenant / production). Dev-only local fallback is gated by policy.
    """
    status = await message.reply_text(
        "🔐 جاري التحقق من التوكن وتشغيل Live Deployment..."
    )
    project_path = pending.get("project_path")
    owner_id = pending.get("owner_user_id")
    entry = pending.get("entry_point") or ""

    def _run_engine():
        from telegram_bot_engine.engines.generators.live_deployment import (
            LiveDeploymentEngine,
        )
        engine = LiveDeploymentEngine()
        return engine.run_live_deployment(
            project_path=project_path,
            bot_token=token,
            owner_user_id=owner_id,
        )

    def _run_runner():
        from telegram_bot_engine.services.live_runner import run_bot_project
        return run_bot_project(
            project_path=project_path,
            bot_token=token,
            entry_hint=entry or None,
            run_seconds=float(os.environ.get("LIVE_RUN_SECONDS", 900)),
        )

    report = None
    try:
        report = await asyncio.to_thread(_run_engine)
    except Exception as e1:
        logger.exception("Live deployment engine failed")
        if not _local_process_fallback_allowed():
            await status.edit_text(
                "❌ فشل Live Deployment في وضع العزل الإجباري (Docker).\n"
                f"{type(e1).__name__}: {sanitize_error(str(e1), max_len=220)}\n"
                "التشغيل المحلي مرفوض في الإنتاج — لا يوجد fallback غير معزول."
            )
            context.user_data.pop("pending_deploy", None)
            return
        logger.warning("Dev isolation allows LiveRunner host-process fallback")
        try:
            report = await asyncio.to_thread(_run_runner)
        except Exception as e2:
            logger.exception("LiveRunner fallback failed")
            await status.edit_text(
                f"❌ فشل Live Deployment: {type(e1).__name__}: {str(e1)[:180]}\n"
                f"fallback: {type(e2).__name__}: {str(e2)[:180]}"
            )
            context.user_data.pop("pending_deploy", None)
            return
    finally:
        token = ""  # noqa: F841

    context.user_data.pop("pending_deploy", None)

    try:
        if hasattr(report, "to_user_text"):
            text_out = report.to_user_text()
        elif hasattr(report, "message"):
            text_out = str(report.message)
        else:
            text_out = str(report)
    except Exception:
        text_out = str(report)[:3500]
    if len(text_out) > 3500:
        text_out = text_out[:3500] + "\n…"
    await status.edit_text(text_out)
