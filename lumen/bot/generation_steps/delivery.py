from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lumen.bot.config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from lumen.bot.helpers import escape_md, make_zip_from_path, split_file_for_telegram, safe_reply_text, safe_edit_text
from lumen.bot.session_store import get_session_store

logger = logging.getLogger("lumen_bot.generation_flow")

from lumen.bot.generation_steps.helpers import _sentry_capture, _smoke_test_project

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
    _quiet = (__import__("os").getenv("QUIET_DELIVERY") or "1").strip().lower() in {"1", "true", "yes", "on"}


    ok_stages = sum(1 for s in stages if getattr(s, "success", False))
    total_stages = len(stages)
    pipeline_warnings: list[str] = []
    summary_lines = [
        f"{'✅' if success else '⚠️'} تم" if _quiet else f"{'✅' if success else '⚠️'} *نتيجة التوليد*",
        f"• النجاح: {'نعم' if success else 'جزئي / فشل'}",
        f"• المراحل الناجحة: {ok_stages}/{total_stages}",
    ]
    if project_path:
        summary_lines.append(f"• المسار: `{escape_md(project_path)}`")
    if meta.get("preset"):
        summary_lines.append(f"• preset: `{escape_md(meta.get('preset'))}`")
    if pipeline_warnings:
        summary_lines.append("• تحذيرات المراحل:")
        summary_lines.extend("  – " + w for w in pipeline_warnings)

    try:
        if _quiet:
            brief = "✅ تم" if success else "⚠️ فشل التوليد"
            await safe_edit_text(status_msg, brief)
        else:
            await safe_edit_text(status_msg, 
                "\n".join(summary_lines)[:GENERATION_STATUS_PREVIEW_LIMIT]
            )
    except Exception:
        logger.exception("status edit failed")

    # Engine presentation: native Rich table from agent metadata/stages
    try:
        from lumen.bot.presentation_send import send_engine_presentation
        bot = getattr(context, "bot", None)
        if bot is None and message is not None:
            bot = getattr(message, "get_bot", lambda: None)()
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        ud = getattr(context, "user_data", None) if context is not None else None
        await send_engine_presentation(
            bot=bot,
            chat_id=chat_id,
            metadata=meta,
            stages=stages,
            user_data=ud if isinstance(ud, dict) else None,
        )
    except Exception:
        logger.exception("engine rich table presentation failed")

    if not success or not project_path:
        await safe_reply_text(message, "لم يُنشأ مشروع جاهز. جرّب وصفاً أوضح.")
        return

    # Mandatory pre-delivery gate: never send a project before deterministic verification.
    try:
        from lumen.engine.services.anti_hallucination import run_anti_hallucination_gate
        _ah = run_anti_hallucination_gate(project_path, user_request=request or "")
        ah = _ah.to_dict()
        ready = bool(_ah.ready_for_token)
        if not ready:
            await safe_reply_text(message, _ah.to_user_text(lang="ar")[:GENERATION_STATUS_PREVIEW_LIMIT])
            return
    except Exception:
        logger.exception("mandatory pre-delivery verification failed")
        await safe_reply_text(message, "❌ تعذر إكمال فحص المشروع قبل التسليم؛ لم يتم إرسال ملف غير متحقق منه.")
        return

    # Ensure every delivered project has a production Dockerfile (image deploy path)
    try:
        from lumen.engine.services.bot_image_builder import write_dockerfile
        write_dockerfile(Path(project_path))
    except Exception:
        logger.exception("dockerfile emit failed")

    # Ensure every delivered project has a clear README with token setup + run instructions.
    # Closes weakness #6: the market judges "does the bot run first time? is there a clear
    # README? is the token easy to set?" — none guaranteed by architecture alone.
    try:
        from lumen.bot.generation_steps.helpers import ensure_project_readme
        ensure_project_readme(project_path, request=request or "")
    except Exception:
        logger.exception("readme ensure failed")

    # Pre-delivery 10s smoke test — code must load before we ship a zip.
    try:
        await safe_reply_text(message, "🧪 جاري اختبار المشروع ~10 ثوانٍ قبل التسليم...")
    except Exception:
        pass
    smoke_ok, smoke_msg = _smoke_test_project(project_path, seconds=10.0)
    if not smoke_ok:
        logger.error("pre-delivery smoke failed: %s", smoke_msg)
        await safe_reply_text(message, 
            "❌ فشل اختبار التشغيل — *لم يُرسل* ملف المشروع.\n"
            "المسار الجذري: الكود لازم يمر على compile + import + handlers قبل التسليم.\n"
            f"التفاصيل: `{escape_md(str(smoke_msg)[:300])}`\n"
            "عدّل الوصف أو أعد المحاولة."
        )
        # Fail closed: never ship a bot that failed the pre-delivery smoke.
        ready = False
        try:
            store = get_session_store()
            store.set(int(user.id), "last_project_path", str(project_path))
            store.set(int(user.id), "last_smoke_ok", False)
            store.set(int(user.id), "ready_for_token", False)
        except Exception:
            pass
        return
    try:
        await safe_reply_text(message, f"✅ اختبار 10 ثوانٍ ناجح ({smoke_msg})")
    except Exception:
        pass

    # Zip delivery — only after anti-hallucination + smoke both passed.
    delivery_ok = False
    last_err = ""
    try:
        zip_path = make_zip_from_path(project_path)
        if not zip_path or not zip_path.exists():
            await safe_reply_text(message, "تم التوليد لكن تعذر إنشاء ملف zip.")
            return
        size_mb = zip_path.stat().st_size / (1024 * 1024)

        async def _send_doc(path: Path, caption: str, filename: str | None = None) -> None:
            """Send a document with retries; prefers InputFile for PTB v21+."""
            import asyncio
            name = filename or path.name
            last: Exception | None = None
            for attempt in range(1, 4):
                try:
                    try:
                        from telegram import InputFile
                        with path.open("rb") as fh:
                            await message.reply_document(
                                document=InputFile(fh, filename=name),
                                caption=caption,
                            )
                    except Exception:
                        # Fallback: path-based upload
                        with path.open("rb") as fh:
                            await message.reply_document(
                                document=fh,
                                filename=name,
                                caption=caption,
                            )
                    return
                except Exception as e:
                    last = e
                    logger.warning("reply_document attempt %s failed: %s", attempt, e)
                    await asyncio.sleep(0.6 * attempt)
            raise last or RuntimeError("document_send_failed")

        if size_mb <= ZIP_MAX_MB:
            await _send_doc(zip_path, "📦 المشروع المُولَّد (zip)")
            delivery_ok = True
            try:
                from lumen.engine.services.object_storage import (
                    enabled as _s3_on,
                    project_archive_key,
                    upload_file as _s3_upload,
                )
                if _s3_on() and user is not None:
                    key = project_archive_key(int(user.id), Path(project_path).name)
                    uri = _s3_upload(zip_path, key)
                    if uri:
                        logger.info("project archive uploaded %s", uri)
            except Exception:
                logger.exception("optional S3 archive upload failed")
        else:
            parts = split_file_for_telegram(zip_path, max_mb=min(45.0, ZIP_MAX_MB))
            if not parts:
                await safe_reply_text(message, 
                    f"❌ تعذر تقسيم ملف المشروع الكبير ({size_mb:.1f} MB)، ولم يكتمل التسليم."
                )
                return
            total = len(parts)
            await safe_reply_text(message, 
                f"📦 المشروع أكبر من رسالة واحدة ({size_mb:.1f} MB)، سأرسل {total} أجزاء مرقمة. "
                "نزّلها كلها وادمجها بالترتيب: cat project.zip.part* > project.zip"
            )
            for index, part in enumerate(parts, 1):
                await _send_doc(part, f"📦 الجزء {index}/{total}", filename=part.name)
            for part in parts:
                try:
                    part.unlink(missing_ok=True)
                except Exception:
                    pass
            delivery_ok = True
    except Exception as exc:
        last_err = f"{type(exc).__name__}: {exc}"
        logger.exception("zip delivery failed: %s", last_err)
        await safe_reply_text(message, 
            "❌ فشل تسليم ملف المشروع بعد نجاح التوليد. لم يتم اعتبار البوت جاهزاً للتشغيل.\n"
            f"سبب التسليم: `{escape_md(last_err[:180])}`"
        )
        return

    # The mandatory gate above is authoritative. Do not overwrite its result
    # with stale/missing metadata from an older generation result shape.
    if not delivery_ok:
        await safe_reply_text(message, "❌ لم يكتمل تسليم ملف المشروع، لذلك لن يتم فتح مسار التشغيل.")
        return
    ready = bool(ready and success)
    ah = ah or meta.get("anti_hallucination") or {}

    # Honest anti-hallucination summary
    try:
        if not ah and project_path:
            from lumen.engine.services.anti_hallucination import (
                run_anti_hallucination_gate,
            )
            _ah = run_anti_hallucination_gate(project_path, user_request=request or "")
            await safe_reply_text(message, _ah.to_user_text(lang="ar"))
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
            if not _quiet:
                for c in (ah.get("verified_commands") or [])[:15]:
                    lines.append(f"  /{c}")
                for e in (ah.get("errors") or [])[:10]:
                    if isinstance(e, dict):
                        lines.append(f"🔴 {e.get('ar') or e.get('code')}")
                    else:
                        lines.append(f"🔴 {e}")
            else:
                n = len(ah.get("verified_commands") or [])
                if ah.get("ok") and ah.get("ready_for_token"):
                    lines = [f"✅ جاهز ({n} أمر)"]
                elif not ah.get("ok"):
                    lines = lines  # keep header + few errors
                    for e in (ah.get("errors") or [])[:3]:
                        if isinstance(e, dict):
                            lines.append(f"🔴 {e.get('ar') or e.get('code')}")
            await safe_reply_text(message, "\n".join(lines)[: (200 if _quiet else GENERATION_STATUS_PREVIEW_LIMIT)])
    except Exception:
        logger.exception("anti_hallucination report failed")

    if ready and context.user_data is not None:
        # Phase 1: do NOT auto-bind TRIAL_CHAT pending_* after generation.
        # Plane is chosen explicitly: post_trial → LiveRunner, post_host → HostingService.
        # Auto pending_live_run caused silent trial when the user pasted a token early.
        try:
            from lumen.bot.ui.project_resolve import resolve_entry_point, bind_active_repo
            _entry = resolve_entry_point(Path(str(project_path)))
        except Exception:
            _entry = "main.py"
        try:
            bind_active_repo(context.user_data, Path(str(project_path)), entry=_entry)
        except Exception:
            pass
        # Clear stale plane bindings from a previous session
        for _k in ("pending_deploy", "pending_live_run", "pending_run", "pending_host"):
            context.user_data.pop(_k, None)
        try:
            if user:
                get_session_store().save(int(user.id), context.user_data)
        except Exception:
            logger.exception("post-generation session persistence failed")
            await safe_reply_text(
                message,
                "⚠️ تم التحقق من المشروع، لكن تعذر حفظ الجلسة. أعد المحاولة.",
            )
            return
        vcmds = meta.get("verified_commands") or ah.get("verified_commands") or []
        cmd_line = ("\nأوامر مؤكدة: " + ", ".join(f"/{c}" for c in vcmds[:12])) if vcmds else ""
        if not _quiet:
            await safe_reply_text(
                message,
                "📦 المشروع جاهز بعد التحقق ضد الهلوسة."
                + cmd_line
                + "\nاختر المسار من الأزرار: تجربة مؤقتة أو استضافة دائمة.",
            )
        else:
            await safe_reply_text(message, "📦 جاهز — اختر تجربة أو استضافة دائمة")

        # Engine UI: explicit plane choice (TRIAL_CHAT vs PERMANENT_HOST)
        try:
            from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
            from lumen.engine.services.ui_state.controller import buttons_for_state
            from lumen.bot.ui.keyboards import build_inline_keyboard
            from lumen.bot.ui.state_store import save_ui_state, persist_ui_session
            ui = EngineUiState(
                phase=EngineUiPhase.GEN_DONE,
                project_ref=str(project_path),
                last_action="generation_done",
            )
            save_ui_state(context.user_data, ui)
            if user:
                persist_ui_session(int(user.id), dict(context.user_data))
            body = (
                "ما التالي؟\n"
                "• تجربة في الشات — تشغيل مؤقت (LiveRunner / TRIAL_CHAT)\n"
                "• استضافة دائمة — Firecracker (HostingService / PERMANENT_HOST)\n"
                "• ZIP أو معاينة الملفات"
            )
            await safe_reply_text(
                message,
                body,
                reply_markup=build_inline_keyboard(
                    buttons_for_state(ui), user_id=int(getattr(user, "id", 0) or 0)
                ),
            )
        except Exception:
            logger.exception("post-generation UI menu failed")

    else:
        await safe_reply_text(message, 
            "⚠️ المشروع اتولّد لكن التحقق ضد الهلوسة رفض تسليمه كجاهز.\n"
            "راجع التقرير أعلاه."
        )

