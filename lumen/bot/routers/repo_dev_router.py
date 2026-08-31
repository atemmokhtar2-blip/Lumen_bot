"""Active-repository development turns (modify/analyze existing clone)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from lumen.bot.helpers import chat_route, make_zip_from_path, safe_edit_text, safe_reply_text

from ..config import OUTPUT_DIR, logger


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
                try:
                    from lumen.bot.ui.actionable_errors import send_actionable_error
                    uid = message.from_user.id if message.from_user else 0
                    await send_actionable_error(
                        status, kind="generic",
                        title="فشل التنفيذ على المستودع",
                        detail=type(e).__name__,
                        user_id=int(uid or 0),
                    )
                except Exception:
                    await safe_edit_text(status, f"❌ فشل التنفيذ على المستودع (`{type(e).__name__}`).")
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
            await safe_edit_text(status, text_out)
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

                # ---- wire edit into the project-memory store (D7) ----
                # Record the structural edit so the engine "remembers" the
                # project's evolving UI (buttons/commands/keyboards) across
                # sessions. This is the real integration point: every
                # successful repo edit now updates the project card.
                try:
                    from lumen.engine.services.semantic_memory.project_memory import (
                        get_project_memory_store,
                    )
                    pms = get_project_memory_store()
                    edit_type = str(getattr(dev, "action", "") or "edit")
                    # extract a target from the contract if available
                    _target = ""
                    try:
                        if dev.contract and getattr(dev, "action", "").endswith("_command"):
                            _cmds = [c.name for c in (dev.contract.commands or [])]
                            _target = f"/{_cmds[-1]}" if _cmds else ""
                    except Exception:
                        _target = ""
                    _pid = str(active["path"])
                    # ensure a project card exists (register_project is idempotent)
                    if not pms.get_card(_pid):
                        _ui = {}
                        try:
                            if dev.contract:
                                _ui = {
                                    "commands": [f"/{c.name}" for c in (dev.contract.commands or [])],
                                }
                        except Exception:
                            _ui = {}
                        pms.register_project(
                            user_id=int(uid or 0),
                            project_id=_pid,
                            label=Path(_pid).name,
                            kind="repo_edit",
                            path=_pid,
                            source_request=(request or "")[:500],
                            ui_elements=_ui,
                        )
                    pms.record_edit(
                        project_id=_pid,
                        edit_type=edit_type,
                        description=(request or "")[:300],
                        target=_target,
                    )
                except Exception:
                    logger.debug("project_memory record_edit after repo edit failed",
                                 exc_info=True)

                # ---- Smart restart: kill the old bot, start the new code ----
                # After ANY successful edit, if a bot was deployed live for
                # this project, kill the old process/container and start the
                # updated version immediately. This makes "edit → see it live"
                # real. Best-effort: never blocks the edit reply on restart.
                try:
                    from lumen.engine.services.hosting import get_hosting_service
                    from lumen.bot.config import OUTPUT_DIR
                    _svc = get_hosting_service(OUTPUT_DIR)
                    _items = list(_svc.list_for_user(int(uid or 0)))
                    _path = str(active.get("path") or "")
                    _restarted = 0
                    for _inst in _items:
                        if _path and str(getattr(_inst, "project_path", "") or "") != _path:
                            continue
                        if str(getattr(_inst, "status", "") or "") not in {"running", "starting"}:
                            continue
                        _res = _svc.stop(instance_id=_inst.instance_id, user_id=int(uid or 0))
                        if getattr(_res, "ok", False):
                            _restarted += 1
                    if _restarted:
                        logger.info(
                            "smart restart after edit: path=%s stopped=%d (re-host to apply code)",
                            _path, _restarted,
                        )
                except Exception:
                    logger.debug("smart restart after repo edit failed",
                                 exc_info=True)

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
