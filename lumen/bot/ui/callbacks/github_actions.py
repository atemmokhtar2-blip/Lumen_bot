"""GitHub connection callback side-effects after apply_action."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen.bot.ui.callbacks.github_actions")


async def handle_github_post_actions(
    *,
    action_id: str,
    result: Any,
    update: Any,
    context: Any,
    uid: int,
) -> None:
    """Run conn_gh_* / gh_* follow-up work. Mutates result/user_data as before."""
    if result.ok and action_id == "conn_gh_select" and uid:
        rid = (result.state.slots.get("gh_selected_id") or "").strip()
        if rid:
            status_msg = None
            try:
                from lumen.engine.services.integrations.connections.token_store import (
                    resolve_cached_repo,
                )
                from lumen.engine.services.integrations.connections.bind_repo import (
                    apply_bind_to_user_data,
                    bind_github_repo,
                )
                import asyncio as _aio

                item = resolve_cached_repo(int(uid), rid)
                if item:
                    result.state.slots["gh_selected_full"] = str(item.get("full_name") or "")[:120]
                    result.state.slots["gh_selected_url"] = str(item.get("html_url") or "")[:200]
                    result.state.slots["gh_selected_branch"] = str(
                        item.get("default_branch") or "main"
                    )[:40]

                label = result.state.slots.get("gh_selected_full") or rid
                result.state.slots["gh_status_line"] = f"جاري سحب {label}…"
                try:
                    _em = update.effective_message
                    if _em is not None:
                        status_msg = await _em.reply_text(
                            f"⏳ جاري سحب وفهم المستودع `{label}` عبر اتصال GitHub…"
                        )
                except Exception:
                    status_msg = None

                bind = await _aio.to_thread(
                    bind_github_repo,
                    int(uid),
                    rid,
                    slots=dict(result.state.slots),
                    run_understand=True,
                )
                if bind.ok and context.user_data is not None:
                    apply_bind_to_user_data(
                        context.user_data,
                        bind,
                        user=update.effective_user,
                    )
                    # Phase 3: readiness gate — missing env before trial/host
                    try:
                        from lumen.engine.services.integrations.connections.readiness import (
                            evaluate_readiness,
                        )
                        rr = evaluate_readiness(
                            active_repo=context.user_data.get("active_repo") or {}
                        )
                        # FORBIDDEN: auto sequential env collection (hallucination source).
                        # Store advisory list only; host waits for bot token.
                        if rr.missing_env:
                            context.user_data["advisory_missing_env"] = list(rr.missing_env)[:20]
                        context.user_data.pop("pending_repo_env", None)
                        if bind.is_runnable and bind.path:
                            context.user_data["pending_host"] = {
                                "project_path": bind.path,
                                "entry_point": str(getattr(bind, "entry_point", "") or ""),
                                "plane": "permanent_host",
                            }
                            context.user_data["last_project_path"] = bind.path
                            ar = dict(context.user_data.get("active_repo") or {})
                            ar["path"] = bind.path
                            context.user_data["active_repo"] = ar
                            result.state.slots["gh_missing_env"] = ",".join(rr.missing_env[:12])
                            result.state.slots["gh_ready"] = "0"
                        else:
                            context.user_data.pop("pending_repo_env", None)
                            result.state.slots["gh_ready"] = "1"
                            result.state.slots.pop("gh_missing_env", None)
                    except Exception:
                        logger.exception("readiness evaluate soft-fail")
                    try:
                        from lumen.bot.session_store import get_session_store

                        get_session_store().save(int(uid), dict(context.user_data))
                    except Exception:
                        logger.exception("persist active_repo after bind failed")
                    result.state.slots["gh_bound_path"] = (bind.path or "")[:200]
                    result.state.slots["gh_bound_url"] = (bind.url or "")[:200]
                    result.state.slots["gh_bound_ok"] = "1"
                    result.state.project_ref = (bind.path or "")[:200]
                    summary = bind.contract_summary or "جاهز"
                    level = str((bind.active_repo or {}).get("understanding_level") or "")
                    brief = (bind.agent_brief or "")[:400]
                    status_bits = [f"✅ مربوط: {bind.full_name or label}", summary]
                    if level:
                        status_bits.append(f"فهم: {level}")
                    if brief:
                        status_bits.append(brief)
                    result.state.slots["gh_status_line"] = "\n".join(status_bits)[:1500]
                    try:
                        from dataclasses import replace as _dc_replace
                        from lumen.engine.services.ui_state.controller import buttons_for_state
                        result = _dc_replace(result, buttons=buttons_for_state(result.state))
                    except Exception:
                        logger.exception("rebuild buttons after bind soft-fail")
                    # Same success UI plane as git_router clone
                    try:
                        from lumen.bot.ui.repo_sections import section_keyboard

                        header = bind.header_ar or f"✅ تم سحب `{bind.full_name or label}`"
                        # Never open sequential env trap — token starts host
                        context.user_data.pop("pending_repo_env", None)
                        adv = list((context.user_data or {}).get("advisory_missing_env") or [])
                        if adv:
                            header += (
                                "\n\n⚙️ متغيرات اختيارية لاحقًا: "
                                + ", ".join(f"`{x}`" for x in adv[:5])
                                + ("…" if len(adv) > 5 else "")
                            )
                        if bind.is_runnable:
                            header += (
                                "\n\n🚀 أرسل توكن البوت من @BotFather للاستضافة على Lumen."
                            )
                            markup = section_keyboard(
                                user_id=int(uid),
                                show_run=True,
                            )
                        else:
                            markup = section_keyboard(
                                user_id=int(uid),
                                show_run=False,
                            )
                        if status_msg is not None:
                            await status_msg.edit_text(header[:4000], reply_markup=markup)
                        else:
                            _em = update.effective_message
                            if _em is not None:
                                await _em.reply_text(header[:4000], reply_markup=markup)
                    except Exception:
                        logger.exception("post-bind UI soft-fail")
                        try:
                            if status_msg is not None:
                                await status_msg.edit_text(
                                    f"✅ تم سحب وربط `{bind.full_name or label}`\n{summary}"
                                )
                        except Exception:
                            pass
                else:
                    result.state.slots["gh_bound_ok"] = "0"
                    result.state.slots["gh_status_line"] = f"❌ {bind.message_ar}"
                    if bind.needs_auth:
                        result.state.slots["gh_connected"] = "0"
                    try:
                        if status_msg is not None:
                            await status_msg.edit_text(f"❌ {bind.message_ar[:500]}")
                    except Exception:
                        pass
            except Exception:
                logger.exception("conn_gh_select bind failed")
                result.state.slots["gh_status_line"] = "❌ فشل ربط المستودع."


