"""Active-repository development turns (modify/analyze existing clone)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..helpers import chat_route, make_zip_from_path


async def try_handle_repo_dev(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled against the active repo."""
    # --- Active repo development (must run before generate_bot) ---
    active = (context.user_data or {}).get("active_repo")
    if active and active.get("path") and Path(active["path"]).exists():
        from lumen.engine.services.repo_dev import (
            handle_repo_request,
            detect_repo_intent,
        )
        action, _ = detect_repo_intent(request)
        # ChatRouter knows system capabilities — prefer it for routing only
        _rt = chat_route(request)
        _cap = getattr(_rt, "capability_id", "") if _rt and getattr(_rt, "ok", False) else ""
        _repo_caps = {
            "static_analysis", "package_health", "upgrade_recommend",
            "upgrade_apply", "repo_develop",
        }
        develop_hints = (
            "أضف", "اضف", "ضيف", "عدل", "عدّل", "اشرح", "الأوامر", "الاوامر",
            "امسح", "أعد", "طور", "طوّر", "هيكل", "command", "add", "explain",
            "stats", "fix", "modify", "ساعد", "تقدر",
            "خطة تطوير", "فجوات", "أين أعد", "تطوير المستودع", "سد فجوات",
            "كمّل", "كمل", "السابق", "اللي فات", "اللي قبل", "نفس البوت",
            "نفس المشروع", "حسّن", "حسن", "أصلح", "اصلح", "extend", "continue",
            "update", "improve", "refactor",
        )
        _cont_flag = bool((context.user_data or {}).get("continuity_plan", {}).get("active"))
        if (
            _cap in _repo_caps
            or action != "unknown"
            or _cont_flag
            or any(h in request.lower() for h in develop_hints)
            or any(h in request for h in develop_hints)
        ):
            status = await message.reply_text("🛠 جاري التنفيذ على المستودع النشط...")
            await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

            # Canonical phrase when ChatRouter recognized capability but wording was soft
            _cap_to_phrase = {
                "static_analysis": "تحليل استاتيكي",
                "package_health": "صحة الحزم",
                "upgrade_recommend": "توصيات الترقية",
                "upgrade_apply": "طبّق الترقيات الآمنة",
                "repo_develop": request,
            }
            _dev_text = request
            if _cap in _cap_to_phrase and action == "unknown":
                _dev_text = _cap_to_phrase[_cap]

            def _run_dev():
                return handle_repo_request(
                    _dev_text,
                    active["path"],
                    contract_dict=active.get("contract"),
                )

            try:
                dev = await asyncio.to_thread(_run_dev)
            except Exception as e:
                logger.exception("RepoDev failed")
                await status.edit_text(f"❌ فشل التنفيذ على المستودع (`{type(e).__name__}`).")
                return True


            if dev.contract is not None:
                context.user_data["active_repo"] = {
                    "path": active["path"],
                    "url": active.get("url"),
                    "contract": dev.contract.model_dump(mode="json"),
                }

            text_out = dev.message
            if dev.changed_files:
                text_out += "\n• ملفات تغيّرت: " + ", ".join(f"`{f}`" for f in dev.changed_files)
            await status.edit_text(text_out)
            try:
                from lumen.engine.services.user_memory import get_user_memory
                mem = get_user_memory(uid, OUTPUT_DIR)
                mem.set_last(
                    intent=request[:200],
                    project_path=str(active.get("path") or ""),
                    capability="continuity_dev",
                )
                note = f"continuity action={getattr(dev, 'action', '')} path={active.get('path')}"
                if dev.changed_files:
                    note += " changed=" + ",".join(dev.changed_files[:8])
                mem.add_turn("note", note, meta={"capability": "continuity_dev", "ok": bool(dev.ok)})
            except Exception:
                logger.exception("memory update after continuity failed")

            if dev.ok and dev.changed_files and active.get("path"):
                try:
                    from lumen.engine.services.advanced_partner import (
                        maybe_snapshot_version,
                    )
                    maybe_snapshot_version(
                        uid,
                        active["path"],
                        label=str(getattr(dev, "action", "") or "edit"),
                        reason=(request or "")[:200],
                        base_dir=OUTPUT_DIR,
                    )
                except Exception:
                    logger.exception("version snapshot failed")

            # If file changed, offer zip of repo
            if dev.ok and dev.changed_files and Path(active["path"]).exists():
                try:
                    zip_path = make_zip_from_path(active["path"])
                    if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                        with open(zip_path, "rb") as f:
                            await message.reply_document(
                                document=f,
                                filename=f"{Path(active['path']).name}_updated.zip",
                                caption="📦 المستودع بعد التعديل",
                            )
                except Exception:
                    logger.exception("zip after repo dev failed")
            return True

    return False
