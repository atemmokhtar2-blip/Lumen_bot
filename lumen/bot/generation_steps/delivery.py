from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lumen.bot.config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from lumen.bot.helpers import escape_md, make_zip_from_path, split_file_for_telegram
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
    # Stage-4 smart narrative (personalized result)
    try:
        from lumen.engine.spec_core.language_understanding.smart_generation import (
            build_narrative,
            format_result_addon,
        )
        from lumen.engine.spec_core.language_understanding.personalization_engine import (
            PersonalizationStyle,
        )
        layers = meta.get("layers") if isinstance(meta.get("layers"), dict) else {}
        style = None
        l6 = layers.get("l6_style") if isinstance(layers.get("l6_style"), dict) else None
        if l6:
            try:
                style = PersonalizationStyle(
                    skill_level=str(l6.get("skill_level") or "beginner"),
                    language_variant=str(l6.get("language_variant") or "ar"),
                    domain=str(l6.get("domain") or "general"),
                )
            except Exception:
                style = None
        bot_name = layers.get("l1_bot_name") or meta.get("preset") or "Bot"
        feats = list(layers.get("l1_features") or layers.get("l2_feature_plan") or [])
        nav = build_narrative(
            request or "",
            style=style,
            intent_name=layers.get("l2_intent"),
            features=feats,
            learning=layers.get("l3_learning") if isinstance(layers.get("l3_learning"), dict) else None,
            memory_snap=layers.get("l2_memory") if isinstance(layers.get("l2_memory"), dict) else None,
            strict=bool(layers.get("l1_strict")),
            bot_name=str(bot_name)[:40],
            success=success,
            feature_count=len(feats) or None,
        )
        baked = meta.get("narrative") if isinstance(meta.get("narrative"), dict) else None
        if baked and baked.get("result_header"):
            addon = (baked.get("result_header") or "") + chr(10) + (baked.get("result_body") or "")
            notes = baked.get("adaptation_notes") or []
            if notes:
                addon += chr(10) + "📌 " + " · ".join(str(x) for x in list(notes)[:4])
        else:
            addon = format_result_addon(nav)
        if addon and not _quiet:
            summary_lines.insert(1, addon.strip())
            menu = list((baked or {}).get("menu_preview") or getattr(nav, "menu_preview", None) or [])[:6]
            if menu:
                summary_lines.insert(2, "القائمة:" + chr(10) + chr(10).join(menu))
    except Exception as exc:
        logger.exception("stage4 narrative failed")
        pipeline_warnings.append("تعذر إنشاء الشرح الذكي للنتيجة؛ تم الاحتفاظ بالكود للتحقق المستقل.")
    # L1–L6 snapshot (so the user sees the intelligence path is active)
    layers = meta.get("layers") if isinstance(meta.get("layers"), dict) else {}
    if layers and not layers.get("layers_error") and not _quiet:
        l1 = layers.get("l1_primary") or layers.get("l1_preset") or "—"
        l2 = layers.get("l2_intent") or "—"
        l2_skill = layers.get("l2_skill") or "—"
        l3_n = len(layers.get("l3_questions") or [])
        l5_n = len(layers.get("l5_build") or [])
        l6 = (layers.get("l6_style") or {}) if isinstance(layers.get("l6_style"), dict) else {}
        l6_dom = l6.get("domain") or "—"
        l6_lang = l6.get("language_variant") or "—"
        summary_lines.append(
            f"• طبقات: L1=`{escape_md(str(l1))}` · L2=`{escape_md(str(l2))}`/{escape_md(str(l2_skill))} · "
            f"L3={l3_n}س · L5={l5_n} · L6=`{escape_md(str(l6_dom))}`/{escape_md(str(l6_lang))}`"
        )
    elif layers.get("layers_error"):
        summary_lines.append(f"• طبقات: ⚠️ `{escape_md(str(layers.get('layers_error'))[:80])}`")
    if errors:
        summary_lines.append("• أخطاء:")
        for e in errors[:8]:
            summary_lines.append(f"  – {escape_md(e)}")

    # Stage-5 mini closed-loop metrics for this user
    try:
        from lumen.engine.spec_core.language_understanding.evaluation_layer import (
            user_feature_stats,
            assign_ab_variant,
        )
        uid = int(user.id) if user else 0
        if uid:
            ust = user_feature_stats(uid)
            ab = assign_ab_variant(uid)
            if ust.get("bots"):
                summary_lines.append(
                    f"• تقييمك: نجاح {float(ust.get('success_rate') or 0)*100:.0f}% "
                    f"من {ust.get('bots')} بوت · A/B=`{ab.variant}`"
                )
            else:
                summary_lines.append(f"• A/B=`{ab.variant}` · أول بوت ليك — التقييم هيتحسّن بعد كام تجربة")
            tw = (layers if isinstance(layers, dict) else {}).get("l5_tweaks") or meta.get("layers", {}).get("l5_tweaks") if isinstance(meta.get("layers"), dict) else None
            # also from narrative path entities not available - use recommend
            from lumen.engine.spec_core.language_understanding.evaluation_layer import recommend_generation_tweaks
            tw = recommend_generation_tweaks(uid)
            if tw.get("avoid_features"):
                summary_lines.append("• هنتجنب: " + ", ".join(tw["avoid_features"][:4]))
            if tw.get("prefer_features"):
                summary_lines.append("• مُفضّل عالميًا: " + ", ".join(tw["prefer_features"][:4]))
    except Exception as exc:
        logger.exception("stage5 mini metrics failed")
        pipeline_warnings.append("تعذر تسجيل مؤشرات A/B لهذه المحاولة؛ لم يؤثر ذلك على فحص الكود.")

    if pipeline_warnings:
        summary_lines.append("• تحذيرات المراحل:")
        summary_lines.extend("  – " + w for w in pipeline_warnings)

    try:
        if _quiet:
            brief = "✅ تم" if success else "⚠️ فشل التوليد"
            await status_msg.edit_text(brief)
        else:
            await status_msg.edit_text(
                "\n".join(summary_lines)[:GENERATION_STATUS_PREVIEW_LIMIT]
            )
    except Exception:
        logger.exception("status edit failed")

    if not success or not project_path:
        await message.reply_text("لم يُنشأ مشروع جاهز. جرّب وصفاً أوضح.")
        return

    # Mandatory pre-delivery gate: never send a project before deterministic verification.
    try:
        from lumen.engine.services.anti_hallucination import run_anti_hallucination_gate
        _ah = run_anti_hallucination_gate(project_path, user_request=request or "")
        ah = _ah.to_dict()
        ready = bool(_ah.ready_for_token)
        if not ready:
            await message.reply_text(_ah.to_user_text(lang="ar")[:GENERATION_STATUS_PREVIEW_LIMIT])
            return
    except Exception:
        logger.exception("mandatory pre-delivery verification failed")
        await message.reply_text("❌ تعذر إكمال فحص المشروع قبل التسليم؛ لم يتم إرسال ملف غير متحقق منه.")
        return

    # Ensure every delivered project has a production Dockerfile (image deploy path)
    try:
        from lumen.engine.services.bot_image_builder import write_dockerfile
        write_dockerfile(Path(project_path))
    except Exception:
        logger.exception("dockerfile emit failed")

    # Pre-delivery 10s smoke test — code must load before we ship a zip.
    try:
        await message.reply_text("🧪 جاري اختبار المشروع ~10 ثوانٍ قبل التسليم...")
    except Exception:
        pass
    smoke_ok, smoke_msg = _smoke_test_project(project_path, seconds=10.0)
    if not smoke_ok:
        logger.error("pre-delivery smoke failed: %s", smoke_msg)
        await message.reply_text(
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
        await message.reply_text(f"✅ اختبار 10 ثوانٍ ناجح ({smoke_msg})")
    except Exception:
        pass

    # Zip delivery — only after anti-hallucination + smoke both passed.
    delivery_ok = False
    last_err = ""
    try:
        zip_path = make_zip_from_path(project_path)
        if not zip_path or not zip_path.exists():
            await message.reply_text("تم التوليد لكن تعذر إنشاء ملف zip.")
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
                await message.reply_text(
                    f"❌ تعذر تقسيم ملف المشروع الكبير ({size_mb:.1f} MB)، ولم يكتمل التسليم."
                )
                return
            total = len(parts)
            await message.reply_text(
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
        await message.reply_text(
            "❌ فشل تسليم ملف المشروع بعد نجاح التوليد. لم يتم اعتبار البوت جاهزاً للتشغيل.\n"
            f"سبب التسليم: `{escape_md(last_err[:180])}`"
        )
        return

    # The mandatory gate above is authoritative. Do not overwrite its result
    # with stale/missing metadata from an older generation result shape.
    if not delivery_ok:
        await message.reply_text("❌ لم يكتمل تسليم ملف المشروع، لذلك لن يتم فتح مسار التشغيل.")
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
            await message.reply_text("\n".join(lines)[: (200 if _quiet else GENERATION_STATUS_PREVIEW_LIMIT)])
    except Exception:
        logger.exception("anti_hallucination report failed")

    if ready and context.user_data is not None:
        pending_payload = {
            "project_path": str(project_path),
            "owner_user_id": user.id if user else None,
            "entry_point": "main.py",
            "run_seconds": int(__import__("os").environ.get("LIVE_RUN_SECONDS", 1800)),  # overridden by plan gate in messages
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
            logger.exception("pending deployment session persistence failed")
            await message.reply_text(
                "⚠️ تم التحقق من المشروع، لكن تعذر حفظ جلسة التشغيل. أعد المحاولة قبل إرسال التوكن."
            )
            return
        vcmds = meta.get("verified_commands") or ah.get("verified_commands") or []
        cmd_line = ("\nأوامر مؤكدة: " + ", ".join(f"/{c}" for c in vcmds[:12])) if vcmds else ""
        if _quiet:
            await message.reply_text("📦 جاهز — أرسل توكن البوت من @BotFather")
        else:
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

