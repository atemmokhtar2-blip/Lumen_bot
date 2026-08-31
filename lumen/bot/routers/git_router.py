"""Git flows for the consumer bot: clone / create / push / pull with token UX."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..helpers import safe_edit_text, safe_reply_text, make_zip_from_path
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


def _validate_user_path(user, path: str) -> str:
    """Validate a project path against the per-user sandbox (anti path-injection).

    SECURITY (Vuln #3): Reuses the canonical ``validate_user_project_path`` from
    ``lumen.api.security`` which uses openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS)
    for kernel-level containment — blocking ``..`` traversal, symlinks, null
    bytes, and UNC/``file:`` schemes. Raises ``ValueError`` on any violation.
    """
    from lumen.api.security import validate_user_project_path
    uid = int(user.id) if user else 0
    return str(validate_user_project_path(uid, path))


async def try_handle_git(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a git flow."""
    try:
        from lumen.engine.services.git_safe_import import (
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
        from lumen.engine.services.chat_router import route_message as _route_msg
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
            await safe_reply_text(message, 
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
            await safe_reply_text(message, 
                f"🔒 لإنشاء المستودع `{name}` على GitHub أحتاج توكن PAT:\n\n"
                "• Classic: `ghp_...` (صلاحية `repo`)\n"
                "• Fine-grained: `github_pat_...`\n\n"
                "أرسل التوكن الآن وسأُنشئ المستودع تلقائياً."
            )
            try:
                from lumen.bot.ui.input_prompt import ask_text_input
                await ask_text_input(message, kind="github_pat")
            except Exception:
                pass

            return True

        _sent = await safe_reply_text(message, f"📦 جاري إنشاء المستودع `{name}`...")


        status = _sent[-1] if _sent else None


        if status is None:


            return
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
            try:
                from lumen.bot.ui.actionable_errors import create_repo_error
                text, markup = create_repo_error(name=name, detail=type(e).__name__, user_id=int(uid or 0))
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import git_op_error
                    text, markup = git_op_error(op="create", user_id=int(uid or 0))
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import send_actionable_error
                        await send_actionable_error(status, kind="create", user_id=int(uid or 0))
                    except Exception:
                        await safe_edit_text(status, "❌ فشل الإنشاء.")
            return True

        if result.ok:
            if result.path:
                context.user_data["active_repo"] = {
                    "path": result.path,
                    "url": result.url or "",
                }
                context.user_data["last_project_path"] = result.path
            context.user_data.pop("pending_create_repo", None)
            try:
                from lumen.bot.ui.rtl_text import code_path, code_url
                body = f"✅ {result.message}"
                if result.url:
                    body += f"\n• الرابط: {code_url(result.url)}"
                if result.path:
                    body += f"\n• المسار: {code_path(result.path)}"
                await safe_edit_text(status, body)
            except Exception:
                await safe_edit_text(status, f"✅ {result.message}")
        elif result.needs_auth:
            context.user_data["pending_create_repo"] = {"name": name, "private": True}
            try:
                from lumen.bot.ui.actionable_errors import needs_auth_prompt
                text, markup = needs_auth_prompt(op="create", user_id=int(uid or 0))
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                await safe_edit_text(status, 
                    "🔒 التوكن غير صالح أو بلا صلاحية `repo`. أرسل PAT صحيح."
                )
        else:
            try:
                from lumen.bot.ui.actionable_errors import create_repo_error
                text, markup = create_repo_error(
                    name=name,
                    detail=str(getattr(result, "message", "") or ""),
                    user_id=int(uid or 0),
                )
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="create", detail=str(result.message or ""), name=name, user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, f"❌ {result.message}")
        return True

    # ── PUSH ──────────────────────────────────────────────────────
    if intent == "push":
        path = _active_path(context)
        if not path:
            await safe_reply_text(message, "مفيش مستودع نشط. اسحب أو أنشئ مستودع أولاً ثم اطلب البوش.")
            return True
        # SECURITY (Vuln #3): validate path against per-user sandbox before git ops
        try:
            path = _validate_user_path(user, path)
        except ValueError:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(message, kind="generic", title="مسار غير صالح", detail="خارج العزل", user_id=int(uid or 0))
            except Exception:
                await safe_reply_text(message, "❌ مسار المشروع غير صالح.")
            return True
        if not token:
            # try without token; if needs_auth, ask
            _sent = await safe_reply_text(message, "📤 جاري الدفع...")

            status = _sent[-1] if _sent else None

            if status is None:

                return
            result = await asyncio.to_thread(lambda: git_push(path, token=None))
            if result.ok:
                await safe_edit_text(status, f"✅ {result.message}")
                return True
            if result.needs_auth or True:
                context.user_data["pending_git_push"] = {"path": path}
                await safe_edit_text(status, 
                    "🔒 الدفع يحتاج صلاحية.\n\n"
                    "أرسل توكن GitHub (PAT) بصلاحية `repo` الآن وسأُكمل البوش."
                )
                return True
        _sent = await safe_reply_text(message, "📤 جاري الدفع بالتوكن...")

        status = _sent[-1] if _sent else None

        if status is None:

            return
        result = await asyncio.to_thread(lambda: git_push(path, token=token))
        if result.ok:
            context.user_data.pop("pending_git_push", None)
            await safe_edit_text(status, f"✅ {result.message}")
        elif result.needs_auth:
            context.user_data["pending_git_push"] = {"path": path}
            try:
                from lumen.bot.ui.actionable_errors import needs_auth_prompt
                text, markup = needs_auth_prompt(user_id=int(uid or 0), op="clone")
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="needs_auth", user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, "🔒 التوكن مرفوض. أرسل PAT.")
        else:
            try:
                from lumen.bot.ui.actionable_errors import git_op_error
                text, markup = git_op_error(op="pull", detail="server_logs", user_id=int(uid or 0))
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="git", detail="op_failed", user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, "❌ فشلت العملية.")
        return True

    # ── PULL (update existing active repo) ────────────────────────
    if intent == "pull" and not extract_repo_url(request):
        path = _active_path(context)
        if not path:
            # fall through to clone if URL present; else guide user
            await safe_reply_text(message, 
                "حدّث مستودع نشط: اسحب مستودع أولاً، أو أرسل رابط المستودع مع «اسحب»."
            )
            return True
        # SECURITY (Vuln #3): validate path against per-user sandbox before git ops
        try:
            path = _validate_user_path(user, path)
        except ValueError:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(message, kind="generic", title="مسار غير صالح", detail="خارج العزل", user_id=int(uid or 0))
            except Exception:
                await safe_reply_text(message, "❌ مسار المشروع غير صالح.")
            return True
        _sent = await safe_reply_text(message, "📥 جاري سحب آخر نسخة...")

        status = _sent[-1] if _sent else None

        if status is None:

            return
        result = await asyncio.to_thread(lambda: git_pull(path, token=token))
        if result.ok:
            await safe_edit_text(status, f"✅ {result.message}")
        elif result.needs_auth:
            context.user_data["pending_clone_auth"] = {
                "url": result.url or "",
                "path": path,
                "op": "pull",
            }
            try:
                from lumen.bot.ui.actionable_errors import needs_auth_prompt
                text, markup = needs_auth_prompt(user_id=int(uid or 0), op="clone")
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import needs_auth_prompt
                    text, markup = needs_auth_prompt(user_id=int(uid or 0), op="clone")
                    await safe_edit_text(status, text, reply_markup=markup)
                except Exception:
                    try:
                        from lumen.bot.ui.actionable_errors import send_actionable_error
                        await send_actionable_error(status, kind="needs_auth", user_id=int(uid or 0))
                    except Exception:
                        await safe_edit_text(status, "🔒 المستودع خاص. أرسل PAT.")
        else:
            try:
                from lumen.bot.ui.actionable_errors import git_op_error
                text, markup = git_op_error(op="pull", detail="server_logs", user_id=int(uid or 0))
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="git", detail="op_failed", user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, "❌ فشلت العملية.")
        return True

    # ── CLONE (default) ───────────────────────────────────────────
    if intent != "clone" and not looks_like_clone_request(request):
        return False

    _sent = await safe_reply_text(message, "📥 جاري سحب المستودع...")


    status = _sent[-1] if _sent else None


    if status is None:


        return
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    dest = _dest_for(uid)

    def _do_clone():
        return smart_clone(request, dest_dir=dest, token=token)

    try:
        result = await asyncio.to_thread(_do_clone)
    except Exception as e:
        logger.exception("Clone failed")
        try:
            from lumen.bot.ui.actionable_errors import private_clone_error
            text, markup = private_clone_error(
                detail=type(e).__name__, user_id=int(uid or 0)
            )
            await safe_edit_text(status, text, reply_markup=markup)
        except Exception:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(status, kind="clone", detail=type(e).__name__, user_id=int(uid or 0))
            except Exception:
                await safe_edit_text(status, f"❌ فشل سحب المستودع (`{type(e).__name__}`).")
        return True

    if result is None:
        try:
            from lumen.bot.ui.actionable_errors import git_op_error
            text, markup = git_op_error(op="clone", detail="empty_result", user_id=int(uid or 0))
            await safe_edit_text(status, text, reply_markup=markup)
        except Exception:
            try:
                from lumen.bot.ui.actionable_errors import send_actionable_error
                await send_actionable_error(status, kind="clone", detail="empty_result", user_id=int(uid or 0))
            except Exception:
                await safe_edit_text(status, "❌ فشل سحب المستودع: نتيجة فارغة")
        return True

    if result.ok:
        if result.path:
            context.user_data["active_repo"] = {
                "path": result.path,
                "url": result.url or "",
            }
            context.user_data["last_project_path"] = result.path
            context.user_data["last_clone_url"] = result.url or ""
            try:
                from lumen.engine.services.repo_understanding.llm_explain import gather_repo_dossier
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
                await safe_edit_text(status, "🔍 جاري فهم المستودع...")
                from lumen.engine.services.repo_understanding import understand_repo

                def _do_u():
                    return understand_repo(result.path, remote_url=result.url or "")

                repo_contract = await asyncio.to_thread(_do_u)
                from lumen.engine.schemas.repo_contract import safe_contract_dict
                _cdata = safe_contract_dict(repo_contract)
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
                try:
                    from lumen.engine.services.repo_understanding.contract import is_runnable_bot
                    _is_runnable = is_runnable_bot(repo_contract)
                except Exception:
                    _is_runnable = bool(_cdata.get("is_telegram_bot"))
                if _is_runnable:
                    entry = ""
                    if getattr(repo_contract, "entry_points", None):
                        entry = repo_contract.entry_points[0].path
                    context.user_data["pending_run"] = {
                        "project_path": result.path,
                        "entry_point": entry,
                        "run_seconds": _plan_live_seconds(user),
                    }
                from lumen.bot.ui.repo_sections import (
                    build_sections_from_contract,
                    section_keyboard,
                    store_sections,
                )
                sections = build_sections_from_contract(
                    repo_contract, path=result.path or "", url=result.url or ""
                )
                store_sections(context.user_data, sections)
                header = sections.get("header") or "✅ تم فهم المستودع"
                if _is_runnable:
                    header += (
                        "\n\n🚀 للتشغيل الحقيقي: أرسل توكن البوت من @BotFather "
                        "أو اضغط الزر — يُحذف السر من المحادثة تلقائياً."
                    )
                await safe_edit_text(status, 
                    header,
                    reply_markup=section_keyboard(
                        user_id=int(uid or 0), show_run=bool(_is_runnable)
                    ),
                )
            except Exception as e:
                logger.exception("Repo understanding failed")
                from lumen.bot.ui.rtl_text import code_path, code_url
                await safe_edit_text(status, 
                    "✅ تم سحب المستودع\n"
                    f"• الرابط: {code_url(result.url or '')}\n"
                    f"• المسار: {code_path(result.path or '')}\n"
                    f"⚠️ الفهم فشل: {type(e).__name__}"
                )

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
            context.user_data["last_clone_url"] = result.url or ""
            try:
                from lumen.bot.ui.actionable_errors import private_clone_error
                text, markup = private_clone_error(
                    url=result.url or "",
                    detail="يتطلب مصادقة",
                    user_id=int(uid or 0),
                )
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                await safe_edit_text(status, 
                    "🔒 المستودع خاص أو يحتاج صلاحية.\n\n"
                    "أرسل الآن توكن GitHub (PAT) بصلاحية `repo`."
                )
        else:
            err = (result.message or "فشل غير معروف")
            if result.stderr:
                err += f"\n`{result.stderr[:300]}`"
            try:
                from lumen.bot.ui.actionable_errors import generic_fail
                text, markup = generic_fail(
                    title="فشل سحب المستودع", detail=err, user_id=int(uid or 0)
                )
                await safe_edit_text(status, text, reply_markup=markup)
            except Exception:
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    await send_actionable_error(status, kind="clone", detail=str(err)[:300], user_id=int(uid or 0))
                except Exception:
                    await safe_edit_text(status, f"❌ {err}")
    return True


class SandboxUnavailable(RuntimeError):
    """Raised when a per-user sandbox cannot be allocated.

    SECURITY: There is NO shared fallback. If the isolated per-user sandbox
    cannot be created, the request MUST fail rather than write to a shared
    directory (which would break tenant/user isolation).
    """


def _dest_for(uid: int) -> Path:
    """Allocate a per-user isolated clone directory.

    Fail-closed: raises :class:`SandboxUnavailable` if the sandbox cannot be
    created. Never falls back to a shared directory.
    """
    from lumen.engine.services.user_sandbox import get_user_sandbox

    try:
        return get_user_sandbox(uid, OUTPUT_DIR).new_clone_dir(label="clone")
    except Exception as exc:  # noqa: BLE001 - re-raise as explicit domain error
        raise SandboxUnavailable(
            f"unable to allocate isolated sandbox for user {uid}: {exc}"
        ) from exc
