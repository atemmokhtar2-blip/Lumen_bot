"""Generation result handling — extracted from messages orchestrator (SRP)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from .helpers import escape_md, make_zip_from_path
from .session_store import get_session_store

logger = logging.getLogger("ai_agent_7h_bot.generation_flow")


async def deliver_generation_result(
    *,
    message,
    status_msg,
    context,
    user,
    request: str,
    result: Any,
) -> None:
    """Format anti-hallucination report, zip, and ready/token prompts."""
    success = bool(getattr(result, "success", False))
    project_path = getattr(result, "project_path", None)
    errors = list(getattr(result, "errors", None) or [])
    stages = list(getattr(result, "stages", None) or [])
    meta = dict(getattr(result, "metadata", None) or {})

    ok_stages = sum(1 for s in stages if getattr(s, "success", False))
    total_stages = len(stages)
    summary_lines = [
        f"{'✅' if success else '⚠️'} *نتيجة التوليد*",
        f"• النجاح: {'نعم' if success else 'جزئي / فشل'}",
        f"• المراحل الناجحة: {ok_stages}/{total_stages}",
    ]
    if project_path:
        summary_lines.append(f"• المسار: `{escape_md(project_path)}`")
    if meta.get("preset"):
        summary_lines.append(f"• preset: `{escape_md(meta.get('preset'))}`")
    if errors:
        summary_lines.append("• أخطاء:")
        for e in errors[:8]:
            summary_lines.append(f"  – {escape_md(e)}")

    try:
        await status_msg.edit_text(
            "\n".join(summary_lines)[:GENERATION_STATUS_PREVIEW_LIMIT]
        )
    except Exception:
        logger.exception("status edit failed")

    if not success or not project_path:
        await message.reply_text("لم يُنشأ مشروع جاهز. جرّب وصفاً أوضح.")
        return

    # Zip delivery
    try:
        zip_path = make_zip_from_path(project_path)
        if zip_path and zip_path.exists():
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            if size_mb < ZIP_MAX_MB:
                await message.reply_document(
                    document=zip_path.open("rb"),
                    filename=zip_path.name,
                    caption="📦 المشروع المُولَّد (zip)",
                )
            else:
                await message.reply_text(
                    f"📦 تم إنشاء المشروع لكن حجم الـ zip كبير ({size_mb:.1f} MB)."
                )
        else:
            await message.reply_text("تم التوليد لكن تعذر إنشاء ملف zip.")
    except Exception:
        logger.exception("zip delivery failed")

    ready = bool(success) and bool(meta.get("ready_for_token", False))
    ah = meta.get("anti_hallucination") or {}

    # Honest anti-hallucination summary
    try:
        if not ah and project_path:
            from telegram_bot_engine.services.anti_hallucination import (
                run_anti_hallucination_gate,
            )
            _ah = run_anti_hallucination_gate(project_path, user_request=request or "")
            await message.reply_text(_ah.to_user_text(lang="ar"))
            ah = _ah.to_dict()
            ready = ready and bool(_ah.ready_for_token)
        elif ah:
            lines = []
            if ah.get("ok") and ah.get("ready_for_token"):
                lines.append("✅ تم التحقق — لا هلوسة هيكلية")
            elif ah.get("ok"):
                lines.append("⚠️ تم التوليد مع تحذيرات")
            else:
                lines.append("❌ فشل التحقق — غير جاهز للتشغيل")
            for c in (ah.get("verified_commands") or [])[:15]:
                lines.append(f"  /{c}")
            for e in (ah.get("errors") or [])[:10]:
                if isinstance(e, dict):
                    lines.append(f"🔴 {e.get('ar') or e.get('code')}")
                else:
                    lines.append(f"🔴 {e}")
            await message.reply_text("\n".join(lines)[:GENERATION_STATUS_PREVIEW_LIMIT])
    except Exception:
        logger.exception("anti_hallucination report failed")

    if ready and context.user_data is not None:
        pending_payload = {
            "project_path": str(project_path),
            "owner_user_id": user.id if user else None,
            "entry_point": "main.py",
            "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 900)),
            "sandbox": True,
        }
        # All three keys so any token-handler path finds the project
        context.user_data["pending_deploy"] = dict(pending_payload)
        context.user_data["pending_live_run"] = dict(pending_payload)
        context.user_data["pending_run"] = dict(pending_payload)
        try:
            if user:
                get_session_store().save(int(user.id), context.user_data)
        except Exception:
            pass
        vcmds = meta.get("verified_commands") or ah.get("verified_commands") or []
        cmd_line = ("\nأوامر مؤكدة: " + ", ".join(f"/{c}" for c in vcmds[:12])) if vcmds else ""
        await message.reply_text(
            "📦 المشروع جاهز بعد التحقق ضد الهلوسة."
            + cmd_line
            + "\n🔑 أرسل توكن البوت من @BotFather لتجربته."
        )
    else:
        await message.reply_text(
            "⚠️ المشروع اتولّد لكن التحقق ضد الهلوسة رفض تسليمه كجاهز.\n"
            "راجع التقرير أعلاه."
        )
