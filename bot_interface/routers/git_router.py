"""Git flows for the consumer bot: clone / create / push / pull with token UX."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..sanitize import sanitize_error
from ..helpers import make_zip_from_path
from ..middlewares.mongo_sync import (
    persist_session as _persist_session,
    plan_live_seconds as _plan_live_seconds,
)


def _active_path(context: ContextTypes.DEFAULT_TYPE) -> str:
    ud = context.user_data or {}
    active = ud.get("active_repo") or {}
    if isinstance(active, dict) and active.get("path"):
        return str(active["path"])
    return str(ud.get("last_project_path") or "").strip()


async def try_handle_git(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a git flow."""
    try:
        from telegram_bot_engine.services.git_safe_import import (
            get_smart_clone,
            get_smart_git,
        )
        _sc = get_smart_clone()
        _sg = get_smart_git()
        looks_like_clone_request = _sc.looks_like_clone_request
        smart_clone = _sc.smart_clone
        extract_repo_url = _sc.extract_repo_url
        extract_token = _sc.extract_token
        detect_git_intent = _sg.detect_git_intent
        looks_like_git_request = _sg.looks_like_git_request
        extract_repo_name = _sg.extract_repo_name
        run_git_intent = getattr(_sg, "run_git_intent", None)
        create_github_repo = _sg.create_github_repo
        git_push = _sg.git_push
        git_pull = _sg.git_pull
    except Exception:
        logger.exception("git modules unavailable")
        return False

    intent = None
    try:
        from telegram_bot_engine.services.chat_router import route_message as _route_msg
        _cr = _route_msg(request)
        if _cr.ok and _cr.capability_id in {"clone_repo", "create_repo", "git_push", "git_pull"}:
            intent = {
                "clone_repo": "clone",
                "create_repo": "create_repo",
                "git_push": "push",
                "git_pull": "pull",
            }.get(_cr.capability_id)
    except Exception:
        _cr = None

    if intent is None:
        intent = detect_git_intent(request)

    if intent is None and not (looks_like_clone_request and looks_like_clone_request(request)):
        return False
    if intent is None:
        intent = "clone"

    uid = int(user.id) if user else 0
    token = extract_token(request)

    # ── CREATE REPO ───────────────────────────────────────────────
    if intent == "create_repo":
        name = extract_repo_name(request)
        if not name:
            await message.reply_text(
                "📦 لإنشاء مستودع، حدّد الاسم.\n"
                "مثال: `أنشئ مستودع my-bot`\n"
                "ومع التوكن: `أنشئ مستودع my-bot` ثم التوكن في نفس الرسالة أو بعده."
            )
            return True
        if not token:
            context.user_data["pending_create_repo"] = {
                "name": name,
                "private": True,
            }
            await message.reply_text(
                f"🔒 لإنشاء المستودع `{name}` على GitHub أحتاج توكن PAT:\n\n"
                "• Classic: `ghp_...` (صلاحية `repo`)\n"
                "• Fine-grained: `github_pat_...`\n\n"
                "أرسل التوكن الآن وسأُنشئ المستودع تلقائياً."
            )
            return True

        status = await message.reply_text(f"📦 جاري إنشاء المستودع `{name}`...")
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

        def _create():
            return run_git_intent(
                request,
                dest_dir=_dest_for(uid),
                token=token,
                repo_name=name,
            )

        try:
            result = await asyncio.to_thread(_create)
        except Exception as e:
            logger.exception("create_repo failed")
            await status.edit_text(f"❌ فشل الإنشاء: {sanitize_error(str(e))}")
            return True

        if result.ok:
            if result.path:
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url or "",
                }
                context.user_data["last_project_path"] = result.path
            context.user_data.pop("pending_create_repo", None)
            await status.edit_text(
                f"✅ {result.message}\n"
                f"• الرابط: {result.url or ''}\n"
                + (f"• المسار المحلي: `{result.path}`\n" if result.path else "")
            )
        elif result.needs_auth:
            context.user_data["pending_create_repo"] = {"name": name, "private": True}
            await status.edit_text(
                "🔒 التوكن غير صالح أو بلا صلاحية `repo`.\nأرسل PAT صحيح لإنشاء المستودع."
            )
        else:
            await status.edit_text(f"❌ {result.message}")
        return True

    # ── PUSH ──────────────────────────────────────────────────────
    if intent == "push":
        path = _active_path(context)
        if not path:
            await message.reply_text("مفيش مستودع نشط. اسحب أو أنشئ مستودع أولاً ثم اطلب البوش.")
            return True
        if not token:
            # try without token; if needs_auth, ask
            status = await message.reply_text("📤 جاري الدفع...")
            result = await asyncio.to_thread(lambda: git_push(path, token=None))
            if result.ok:
                await status.edit_text(f"✅ {result.message}")
                return True
            if result.needs_auth or True:
                context.user_data["pending_git_push"] = {"path": path}
                await status.edit_text(
                    "🔒 الدفع يحتاج صلاحية.\n\n"
                    "أرسل توكن GitHub (PAT) بصلاحية `repo` الآن وسأُكمل البوش."
                )
                return True
        status = await message.reply_text("📤 جاري الدفع بالتوكن...")
        result = await asyncio.to_thread(lambda: git_push(path, token=token))
        if result.ok:
            context.user_data.pop("pending_git_push", None)
            await status.edit_text(f"✅ {result.message}")
        elif result.needs_auth:
            context.user_data["pending_git_push"] = {"path": path}
            await status.edit_text("🔒 التوكن مرفوض. أرسل PAT بصلاحية `repo`.")
        else:
            await status.edit_text(f"❌ {sanitize_error(result.message)}")
        return True

    # ── PULL (update existing active repo) ────────────────────────
    if intent == "pull" and not extract_repo_url(request):
        path = _active_path(context)
        if not path:
            # fall through to clone if URL present; else guide user
            await message.reply_text(
                "حدّث مستودع نشط: اسحب مستودع أولاً، أو أرسل رابط المستودع مع «اسحب»."
            )
            return True
        status = await message.reply_text("📥 جاري سحب آخر نسخة...")
        result = await asyncio.to_thread(lambda: git_pull(path, token=token))
        if result.ok:
            await status.edit_text(f"✅ {result.message}\n`{result.path}`")
        elif result.needs_auth:
            context.user_data["pending_clone_auth"] = {
                "url": result.url or "",
                "path": path,
                "op": "pull",
            }
            await status.edit_text(
                "🔒 المستودع خاص.\nأرسل توكن GitHub (PAT) بصلاحية `repo`."
            )
        else:
            await status.edit_text(f"❌ {sanitize_error(result.message)}")
        return True

    # ── CLONE (default) ───────────────────────────────────────────
    if intent != "clone" and not looks_like_clone_request(request):
        return False

    status = await message.reply_text("📥 جاري سحب المستودع...")
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    dest = _dest_for(uid)

    def _do_clone():
        return smart_clone(request, dest_dir=dest, token=token)

    try:
        result = await asyncio.to_thread(_do_clone)
    except Exception as e:
        logger.exception("Clone failed")
        await status.edit_text(f"❌ فشل سحب المستودع: {type(e).__name__}: {sanitize_error(str(e))}")
        return True

    if result is None:
        await status.edit_text("❌ فشل سحب المستودع: نتيجة فارغة من محرك السحب")
        return True

    if result.ok:
        lines = [
            f"✅ تم سحب المستودع",
            f"• الرابط: {result.url or ''}",
            f"• المسار: `{result.path or ''}`",
        ]
        if result.path:
            context.user_data["active_repo"] = {
                "path": result.path,
                "url": result.url or "",
            }
            context.user_data["last_project_path"] = result.path
            # Bind Grok context: pre-compute measurable dossier for free-form Q&A
            try:
                from telegram_bot_engine.services.repo_understanding.llm_explain import gather_repo_dossier
                _dos = gather_repo_dossier(Path(result.path))
                context.user_data["active_repo"]["dossier"] = {
                    "root": _dos.get("root"),
                    "tree": _dos.get("tree"),
                    "facts": _dos.get("facts"),
                    "key_file_names": list((_dos.get("key_files") or {}).keys()),
                }
                context.user_data["active_repo"]["facts"] = _dos.get("facts") or {}
            except Exception:
                logger.exception("post-clone dossier gather failed")
            _persist_session(user, context)
            try:
                await status.edit_text("\n".join(lines + ["", "🔍 جاري فهم المستودع..."]))
                from telegram_bot_engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                from telegram_bot_engine.schemas.repo_contract import safe_contract_dict
                _cdata = safe_contract_dict(repo_contract)
                # Merge — never wipe dossier/facts already bound for Grok
                _prev = dict(context.user_data.get("active_repo") or {})
                _prev.update(
                    {
                        "path": result.path,
                        "url": result.url or _prev.get("url") or "",
                        "contract": _cdata,
                        "bound_for_grok": True,
                    }
                )
                context.user_data["active_repo"] = _prev
                if _cdata.get("summary"):
                    lines.append(f"• الملخص: {str(_cdata.get('summary'))[:300]}")
                _eps = _cdata.get("entry_points") or []
                _ep_show = []
                for e in _eps[:5]:
                    if isinstance(e, dict) and e.get("path"):
                        _ep_show.append(str(e["path"]))
                if _ep_show:
                    lines.append("• نقاط الدخول: " + ", ".join(f"`{x}`" for x in _ep_show))
                if _cdata.get("is_telegram_bot"):
                    lines.append("• يبدو كبوت تيليجرام")
                try:
                    from telegram_bot_engine.services.repo_understanding.contract import is_runnable_bot
                    _is_runnable = is_runnable_bot(repo_contract)
                except Exception:
                    _is_runnable = False
                if _is_runnable:
                    entry = ""
                    if repo_contract.entry_points:
                        entry = repo_contract.entry_points[0].path
                    context.user_data["pending_run"] = {
                        "project_path": result.path,
                        "entry_point": entry,
                        "run_seconds": _plan_live_seconds(user),
                    }
                    lines.append("")
                    lines.append(
                        "🚀 *للتشغيل الحقيقي:* أرسل الآن توكن البوت من @BotFather\n"
                        "(تحقق + تثبيت تبعيات + تشغيل — بدون نجاح وهمي)"
                    )
            except Exception as e:
                logger.exception("Repo understanding failed")
                lines.append(f"⚠️ السحب نجح لكن الفهم فشل: {type(e).__name__}")

        await status.edit_text("\n".join(lines))
        if result.path and Path(result.path).exists():
            try:
                zip_path = make_zip_from_path(result.path)
                if zip_path and zip_path.exists() and zip_path.stat().st_size < 45 * 1024 * 1024:
                    with open(zip_path, "rb") as f:
                        await message.reply_document(
                            document=f,
                            filename=f"{Path(result.path).name}.zip",
                            caption="📦 نسخة من المستودع المسحوب",
                        )
            except Exception:
                logger.exception("Failed to zip cloned repo")
    else:
        if getattr(result, "needs_auth", False):
            context.user_data["pending_clone_auth"] = {
                "url": result.url or "",
            }
            await status.edit_text(
                "🔒 المستودع خاص أو يحتاج صلاحية.\n\n"
                "أرسل الآن *توكن GitHub* (PAT) بصلاحية `repo`:\n"
                "• Classic: ghp_...\n"
                "• Fine-grained: github_pat_...\n\n"
                "بعدها هُعاد السحب تلقائياً."
            )
        else:
            err = (result.message or "فشل غير معروف")
            if result.stderr:
                err += f"\n`{result.stderr[:300]}`"
            await status.edit_text(f"❌ {err}")
    return True


def _dest_for(uid: int) -> Path:
    try:
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
        return get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="clone")
    except Exception:
        dest = Path(OUTPUT_DIR) / "clones"
        dest.mkdir(parents=True, exist_ok=True)
        return dest
