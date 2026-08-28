"""Chat runtime token handlers — two planes (do not mix).

  TRIAL_CHAT      → handle_live_run_token  → LiveRunner (ephemeral, auto-stop)
  PERMANENT_HOST  → pending_host / HostService (Firecracker, long-running)

  handle_live_deploy_token routes to permanent HostService (not trial).
"""

from __future__ import annotations

import asyncio
import os
import time

from .config import logger, LIVE_RUN_SECONDS
from .helpers import escape_md, safe_edit_text


async def handle_live_run_token(message, context, token: str, pending: dict) -> None:
    """TRIAL_CHAT plane: short try-in-chat. Not permanent hosting."""
    status = await message.reply_text(
        "🧪 تجربة مؤقتة (ليست استضافة دائمة)\n🔐 1/4 التحقق من التوكن..."
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
        from lumen.engine.services.live_runner import run_bot_project
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
        await status.edit_text(f"❌ فشل التشغيل الحي (`{type(e).__name__}`).")
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
    """PERMANENT_HOST plane: durable hosting via HostService (Firecracker in production)."""
    from lumen.bot.config import OUTPUT_DIR

    status = await message.reply_text(
        "🏠 استضافة دائمة (Firecracker في الإنتاج)\n🔐 جاري التحقق من التوكن وبدء الاستضافة..."
    )
    project_path = pending.get("project_path") or ""
    owner_id = pending.get("owner_user_id") or (
        message.from_user.id if message.from_user else 0
    )

    def _run_host():
        from lumen.engine.services.hosting import get_hosting_service
        from lumen.engine.services.runtime_planes import RuntimePlane

        svc = get_hosting_service(OUTPUT_DIR)
        return svc.start(
            user_id=int(owner_id or 0),
            project_path=project_path,
            bot_token=token,
        )

    try:
        result = await asyncio.to_thread(_run_host)
    except Exception as e1:
        logger.exception("permanent host start failed")
        await status.edit_text(
            "❌ فشلت الاستضافة الدائمة.\n"
            f"رمز: `{type(e1).__name__}`\n"
            "التجربة المؤقتة في الشات مسار منفصل (live_run)."
        )
        context.user_data.pop("pending_deploy", None)
        return
    finally:
        token = ""  # noqa: F841

    context.user_data.pop("pending_deploy", None)
    text_out = result.to_user_text() if hasattr(result, "to_user_text") else str(result)
    if len(text_out) > 3500:
        text_out = text_out[:3500] + "\n…"
    await status.edit_text(text_out)
