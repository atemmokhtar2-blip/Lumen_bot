"""Generation result handling — extracted from messages orchestrator (SRP)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from .helpers import escape_md, make_zip_from_path, split_file_for_telegram
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
    pipeline_warnings: list[str] = []
    summary_lines = [
        f"{'✅' if success else '⚠️'} *نتيجة التوليد*",
        f"• النجاح: {'نعم' if success else 'جزئي / فشل'}",
        f"• المراحل الناجحة: {ok_stages}/{total_stages}",
    ]
    if project_path:
        summary_lines.append(f"• المسار: `{escape_md(project_path)}`")
    if meta.get("preset"):
        summary_lines.append(f"• preset: `{escape_md(meta.get('preset'))}`")
    # Stage-4 smart narrative (personalized result)
    try:
        from telegram_bot_engine.spec_core.language_understanding.smart_generation import (
            build_narrative,
            format_result_addon,
        )
        from telegram_bot_engine.spec_core.language_understanding.personalization_engine import (
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
        if addon:
            summary_lines.insert(1, addon.strip())
            menu = list((baked or {}).get("menu_preview") or getattr(nav, "menu_preview", None) or [])[:6]
            if menu:
                summary_lines.insert(2, "القائمة:" + chr(10) + chr(10).join(menu))
    except Exception as exc:
        logger.exception("stage4 narrative failed")
        pipeline_warnings.append("تعذر إنشاء الشرح الذكي للنتيجة؛ تم الاحتفاظ بالكود للتحقق المستقل.")
    # L1–L6 snapshot (so the user sees the intelligence path is active)
    layers = meta.get("layers") if isinstance(meta.get("layers"), dict) else {}
    if layers and not layers.get("layers_error"):
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
        from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import (
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
            from telegram_bot_engine.spec_core.language_understanding.evaluation_layer import recommend_generation_tweaks
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
        from telegram_bot_engine.services.anti_hallucination import run_anti_hallucination_gate
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

    # Zip delivery, only after the pre-delivery gate passes.
    try:
        zip_path = make_zip_from_path(project_path)
        if zip_path and zip_path.exists():
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            if size_mb <= ZIP_MAX_MB:
                with zip_path.open("rb") as document:
                    await message.reply_document(
                        document=document,
                        filename=zip_path.name,
                        caption="📦 المشروع المُولَّد (zip)",
                    )
            else:
                parts = split_file_for_telegram(zip_path, max_mb=min(45.0, ZIP_MAX_MB))
                if not parts:
                    await message.reply_text(
                        f"❌ تعذر تقسيم ملف المشروع الكبير ({size_mb:.1f} MB)، ولم يتم إسقاط التسليم."
                    )
                else:
                    total = len(parts)
                    await message.reply_text(
                        f"📦 المشروع أكبر من رسالة واحدة ({size_mb:.1f} MB)، سأرسل {total} أجزاء مرقمة. "
                        "نزّلها كلها وادمجها بالترتيب: cat project.zip.part* > project.zip"
                    )
                    for index, part in enumerate(parts, 1):
                        with part.open("rb") as document:
                            await message.reply_document(
                                document=document,
                                filename=part.name,
                                caption=f"📦 الجزء {index}/{total}",
                            )
                    for part in parts:
                        part.unlink(missing_ok=True)
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
