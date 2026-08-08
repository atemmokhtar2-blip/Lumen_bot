"""Live run and live deployment token handlers."""

from __future__ import annotations

import asyncio
import os
import time

from .config import logger
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
        or os.environ.get("LIVE_RUN_SECONDS", 900)
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
        from telegram_bot_engine.formal_engine.services.live_runner import run_bot_project
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
        await status.edit_text(f"❌ فشل التشغيل الحي: {type(e).__name__}: {str(e)[:200]}")
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


async def handle_live_deploy_token(message, context, token: str, pending: dict) -> None:
    """Spec 065: validate token, deploy, health-check, functional tests."""
    status = await message.reply_text(
        "🔐 جاري التحقق من التوكن وتشغيل Live Deployment..."
    )
    project_path = pending.get("project_path")
    owner_id = pending.get("owner_user_id")

    def _run():
        from telegram_bot_engine.engines.generators.live_deployment import (
            LiveDeploymentEngine,
        )
        engine = LiveDeploymentEngine()
        return engine.run_live_deployment(
            project_path=project_path,
            bot_token=token,
            owner_user_id=owner_id,
        )

    try:
        report = await asyncio.to_thread(_run)
    except Exception as e:
        logger.exception("Live deployment failed")
        await status.edit_text(f"❌ فشل Live Deployment: {type(e).__name__}")
        return
    finally:
        token = ""  # noqa: F841

    context.user_data.pop("pending_deploy", None)

    tv = report.token_validation
    lines = [report.message if hasattr(report, "message") else str(report)]
    try:
        text_out = report.to_user_text() if hasattr(report, "to_user_text") else "\n".join(lines)
    except Exception:
        text_out = "\n".join(str(x) for x in lines)
    if len(text_out) > 3500:
        text_out = text_out[:3500] + "\n…"
    await status.edit_text(text_out)
