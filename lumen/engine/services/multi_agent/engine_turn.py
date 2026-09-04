"""Unified engine turn — every natural-language message owned by agents.

Telegram (or any channel) must call ``handle_user_turn`` instead of a
standalone chat model. Flow:

  user text
    → RouterAgent (capability + tool selection)
    → execute_tool_gated  OR  signal generate/refine  OR  repo-bound understand
    → final_message + side-effects on user_data

No conversational LLM path. No fake success.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .roles.router import RouterAgent
from .state import AgentRole, AgentState, AgentStatus
from .tools import execute_tool_gated, select_tool

logger = logging.getLogger(__name__)


@dataclass
class EngineTurnResult:
    """Outcome of one agent-owned user turn."""

    ok: bool
    reply: str = ""
    action: str = ""  # "", "generate", "refine", "awaiting_confirm", "tool"
    state: Optional[AgentState] = None
    user_data_updates: dict[str, Any] = field(default_factory=dict)
    tool: str = ""
    capability_id: str = ""
    generate_request: str = ""
    needs_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reply": self.reply,
            "action": self.action,
            "tool": self.tool,
            "capability_id": self.capability_id,
            "generate_request": self.generate_request,
            "needs_confirmation": self.needs_confirmation,
            "state_id": getattr(self.state, "state_id", None) if self.state else None,
            "user_data_updates": dict(self.user_data_updates or {}),
        }


_GENERATE_CAPS = frozenset({"generate_bot", "refine_bot"})
_HOST_CAPS = frozenset({"host_start", "host_stop", "host_status", "host_diagnose"})
_GIT_CAPS = frozenset({"clone_repo", "create_repo", "git_push", "git_pull"})
_REPO_CAPS = frozenset({
    "repo_understand", "repo_inspect", "repo_modify",
    "static_analysis", "package_health", "upgrade_recommend", "upgrade_apply",
    "repo_develop",
})


def _active_repo_path(user_data: dict[str, Any] | None) -> str:
    if not isinstance(user_data, dict):
        return ""
    ar = user_data.get("active_repo")
    if not isinstance(ar, dict):
        return ""
    path = str(ar.get("path") or "").strip()
    if path and Path(path).is_dir():
        return path
    return ""


def _llm_available() -> bool:
    try:
        from lumen.engine.services.cline_runtime.model_router import select_model
        choice = select_model(task="plan")
        return bool(choice and choice.provider and choice.provider != "none" and choice.key_present())
    except Exception:
        return False


def _agent_llm_decide(text: str, *, repo_path: str = "", user_id: int = 0) -> dict[str, Any]:
    """One agent brain step via model_catalog → select_model → agent_brain.decide.

    Returns dict: tool, params, reply, provider, error.
    Never invents a static capabilities menu.
    """
    try:
        from lumen.engine.services.cline_runtime.model_router import select_model
        from lumen.engine.services.cline_runtime import agent_brain
        from lumen.engine.services.tool_runtime.registry import list_tool_names, tool_catalog_for_prompt
    except Exception as exc:
        return {"tool": "", "params": {}, "reply": "", "error": f"import:{type(exc).__name__}"}

    choice = select_model(task="plan")
    if not choice or choice.provider == "none" or not choice.key_present():
        return {
            "tool": "",
            "params": {},
            "reply": "",
            "error": "no_llm_key",
            "provider": getattr(choice, "provider", ""),
        }

    catalog = ""
    try:
        catalog = tool_catalog_for_prompt()
    except Exception:
        catalog = ", ".join(list_tool_names())

    system = (
        "You are the Lumen engine agent. You own the user turn.\n"
        "Pick at most ONE tool from the catalog and fill params, OR answer briefly in Arabic if no tool fits.\n"
        "Never invent success. Never list a menu of all capabilities.\n"
        "JSON only: {\"tool\": \"name_or_empty\", \"params\": {}, \"reply\": \"arabic text\"}\n"
        f"Tools:\n{catalog}\n"
        + (f"Active repo path: {repo_path}\n" if repo_path else "")
    )
    user = (text or "")[:4000]
    provider = choice.provider
    _charge_token = None
    try:
        from lumen.platform.credits.llm_live import (
            InsufficientCreditsError,
            bind_charge_context,
            clear_charge_context,
            tenant_id_from_user,
        )
    except Exception:
        InsufficientCreditsError = type("InsufficientCreditsError", (Exception,), {})  # type: ignore
        def bind_charge_context(**kwargs):
            return None
        def clear_charge_context(*a, **k):
            return None
        def tenant_id_from_user(uid):
            return f"tg:{int(uid)}" if int(uid or 0) else ""
    try:
        _charge_token = bind_charge_context(
            tenant_id=tenant_id_from_user(user_id),
            user_id=int(user_id or 0),
            state_id=f"engine_turn:{int(user_id or 0)}",
            step=0,
            call_index=0,
        )
        # Metered path: charge context bound → _record_usage deducts
        # Resolve active conversation for this Telegram user
        _conv_id = ""
        try:
            from lumen.platform.conversations import get_conversation_service
            _conv = get_conversation_service().ensure_active(int(user_id or 0))
            _conv_id = _conv.id
        except Exception:
            _conv_id = ""
        decision = agent_brain.decide(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            choice=choice,
            task="plan",
            user_id=int(user_id or 0),
            conversation_id=_conv_id,
        )
        provider = str(decision.get("provider") or provider)
        raw = str(decision.get("raw") or "")
        if decision.get("tool") or decision.get("reply") or decision.get("thought") or decision.get("parse_ok"):
            tool = str(decision.get("tool") or "").strip()
            params = decision.get("params") or decision.get("args") or {}
            if not isinstance(params, dict):
                params = {}
            reply = str(
                decision.get("reply") or decision.get("thought") or decision.get("summary") or ""
            ).strip()
            known = set(list_tool_names()) | {"generate_bot", "refine_bot"}
            if tool and tool not in known:
                reply = (reply + f"\n(unknown tool: {tool})").strip() if reply else f"أداة غير معروفة: {tool}"
                tool = ""
            return {
                "tool": tool,
                "params": params,
                "reply": reply,
                "provider": provider,
                "model_id": decision.get("model_id") or choice.model_id,
                "error": decision.get("error") or "",
            }
        # Fall through to parse raw if decide returned soft parse fail
        if not raw and decision.get("raw"):
            raw = str(decision.get("raw") or "")
        if not raw:
            # decide may put content only in normalized fields
            return {
                "tool": str(decision.get("tool") or "").strip(),
                "params": decision.get("params") if isinstance(decision.get("params"), dict) else {},
                "reply": str(decision.get("reply") or decision.get("thought") or "").strip(),
                "provider": provider,
                "model_id": decision.get("model_id") or choice.model_id,
                "error": str(decision.get("error") or ""),
            }
    except InsufficientCreditsError as ice:
        return {
            "tool": "",
            "params": {},
            "reply": "رصيدك غير كافٍ لتغطية تكلفة الذكاء الاصطناعي. اشحن رصيدك ثم أعد المحاولة.",
            "error": "insufficient_credits",
            "provider": provider,
            "needed": getattr(ice, "needed", 0),
            "available": getattr(ice, "available", 0),
        }
    except Exception as exc:
        if type(exc).__name__ == "InsufficientCreditsError":
            return {
                "tool": "",
                "params": {},
                "reply": "رصيدك غير كافٍ لتغطية تكلفة الذكاء الاصطناعي. اشحن رصيدك ثم أعد المحاولة.",
                "error": "insufficient_credits",
                "provider": provider,
            }
        logger.exception("agent llm call failed provider=%s", provider)
        return {
            "tool": "",
            "params": {},
            "reply": "",
            "error": f"llm:{type(exc).__name__}",
            "provider": provider,
        }
    finally:
        try:
            clear_charge_context(_charge_token)
        except Exception:
            pass

    obj = agent_brain._extract_json_object(raw) or {}
    obj = agent_brain._extract_json_object(raw) or {}
    tool = str(obj.get("tool") or obj.get("tool_name") or obj.get("action") or "").strip()
    params = obj.get("params") or obj.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    reply = str(obj.get("reply") or obj.get("summary") or obj.get("message") or "").strip()
    known = set(list_tool_names()) | {"generate_bot", "refine_bot"}
    if tool and tool not in known:
        # treat unknown tool name as reply text
        if not reply:
            reply = tool
        tool = ""
    if not reply and not tool and raw:
        reply = str(raw).strip()[:2000]
    return {
        "tool": tool,
        "params": params,
        "reply": reply[:4000],
        "provider": provider,
        "error": "",
        "raw": str(raw)[:500],
    }



def _spec_is_underspecified(text: str) -> bool:
    """True when user wants a bot but gave no real product brief for the agent to build."""
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 28:
        return True
    low = t.lower()
    # Verb + bot only, no product detail
    vague = bool(
        re.search(
            r"(?:عايز|عاوز|أريد|ابغى|اعمل|أنشئ|انشئ|ابني|ول[ّ]?د|generate|create|make).{0,40}(?:بوت|bot)",
            low,
            re.I,
        )
    )
    has_detail = bool(
        re.search(
            r"/[a-zA-Z]|أمر|اوامر|أوامر|ترحيب|حظر|متجر|حجز|قناة|جروب|مجموعة|admin|"
            r"welcome|ban|shop|book|channel|group|feature|ميز|يرد|يرسل|يشترك",
            t,
            re.I,
        )
    )
    if vague and not has_detail and len(t) < 100:
        return True
    return False


def handle_user_turn(
    text: str,
    *,
    user_id: int = 0,
    user_data: dict[str, Any] | None = None,
) -> EngineTurnResult:
    """Run one full agent-owned turn. Always returns a result (never None)."""
    text = (text or "").strip()
    ud = dict(user_data or {})
    if not text:
        return EngineTurnResult(
            ok=False,
            reply="اكتب طلبك بوضوح (توليد بوت، سحب مستودع، فهم المشروع، استضافة…).",
            action="",
        )

    state = AgentState(
        user_id=int(user_id or 0),
        user_text=text[:8000],
        spec_request=text[:8000],
    )
    repo_path = _active_repo_path(ud)
    if repo_path:
        state.extensions["work_dir"] = repo_path
        state.extensions["active_repo"] = dict(ud.get("active_repo") or {})

    # 1) Router agent — sole intent authority for this turn
    try:
        state = RouterAgent().run(state, context={"user_data": ud, "user_id": int(user_id or 0)})
    except Exception as exc:
        logger.exception("RouterAgent failed")
        return EngineTurnResult(
            ok=False,
            reply=f"فشل توجيه الطلب داخل المحرك: {type(exc).__name__}",
            state=state,
        )

    cap = str(state.capability_id or state.user_intent or "").strip()
    tool = str(select_tool(state) or cap or "").strip()
    params = dict(state.route_params or {})
    params.setdefault("text", text)
    params.setdefault("raw_text", text)
    if repo_path:
        params.setdefault("path", repo_path)

    # 2) Generate / refine → only when the brief is enough for agents to build
    if cap in _GENERATE_CAPS or tool in _GENERATE_CAPS:
        action = "refine" if cap == "refine_bot" or tool == "refine_bot" else "generate"
        if action == "generate" and _spec_is_underspecified(text):
            # World-class: agents clarify — never jump to HITL on empty plan
            decision = _agent_llm_decide(
                (
                    f"المستخدم طلب توليد بوت بمواصفة ناقصة:\n«{text}»\n\n"
                    "لا تبدأ التوليد. اسأل بالعربية 2–3 أسئلة قصيرة وواضحة لمعرفة: "
                    "وظيفة البوت، الأوامر الأساسية، والجمهور (جروب/خاص/قناة). "
                    "JSON: tool=\"\", reply=الأسئلة فقط."
                ),
                repo_path=repo_path,
                user_id=int(user_id or 0),
            )
            reply = (decision.get("reply") or "").strip()
            if decision.get("error") == "insufficient_credits":
                reply = str(
                    decision.get("reply")
                    or "رصيدك غير كافٍ لتغطية تكلفة الذكاء الاصطناعي. اشحن رصيدك ثم أعد المحاولة."
                )
                state.final_message = reply
                return EngineTurnResult(ok=False, reply=reply[:4000], action="", state=state, tool="", capability_id="generate_bot")
            if decision.get("error") == "no_llm_key":
                reply = (
                    "المواصفة ناقصة للتوليد.\n"
                    "اكتب ماذا يفعل البوت والأوامر (مثال: بوت جروب فيه /start ترحيب و /ban حظر)."
                )
            elif decision.get("error") or not reply:
                reply = (
                    "تمام — عايز أبني بوت، بس محتاج تفاصيل:\n"
                    "1) البوت هيعمل إيه؟\n"
                    "2) أوامر أساسية (مثل /start /help)؟\n"
                    "3) لجروب ولا خاص؟\n"
                    "اكتب الوصف في رسالة واحدة وبعدها أبدأ البناء."
                )
            state.final_message = reply
            return EngineTurnResult(
                ok=True,
                reply=reply[:4000],
                action="clarify",
                state=state,
                tool="",
                capability_id="generate_bot",
                user_data_updates={
                    "awaiting_bot_spec": True,
                    "last_bot_request": text[:2000],
                    "translated_source": "engine_turn_clarify",
                },
            )
        return EngineTurnResult(
            ok=True,
            reply="",
            action=action,
            state=state,
            tool=tool or cap,
            capability_id=cap,
            generate_request=text,
            user_data_updates={
                "force_generate_once": True,
                "translated_source": "engine_turn",
                "last_bot_request": text[:2000],
                "multi_agent_state_id": state.state_id,
            },
        )

    # 3) Bound repo + soft/unknown intent → agents measure the repo (not chat)
    if tool in {"chat_or_other", ""} and repo_path:
        tool = "repo_understand"
        cap = "repo_understand"
        params["path"] = repo_path
        state.capability_id = "repo_understand"
        state.user_intent = "repo_understand"

    # 4) Soft intent → agent LLM (GROQ_API_KEYS / GEMINI via model_router) then execute
    if tool in {"chat_or_other", ""}:
        decision = _agent_llm_decide(text, repo_path=repo_path, user_id=int(user_id or 0))
        if decision.get("error") == "insufficient_credits":
            msg = str(
                decision.get("reply")
                or "رصيدك غير كافٍ لتغطية تكلفة الذكاء الاصطناعي. اشحن رصيدك ثم أعد المحاولة."
            )
            state.final_message = msg
            return EngineTurnResult(ok=False, reply=msg[:4000], action="", state=state, tool="", capability_id=cap)
        if decision.get("error") == "no_llm_key":
            msg = (
                "المحرك لا يجد مفتاح LLM على السيرفر.\n"
                "أضف GROQ_API_KEYS (أو GROQ_API_KEY) في متغيرات الاستضافة ثم أعد تشغيل الخدمة."
            )
            state.final_message = msg
            return EngineTurnResult(ok=False, reply=msg, action="", state=state, tool="", capability_id=cap)
        if decision.get("error"):
            msg = f"فشل عقل الوكيل ({decision.get('provider') or '?'}): {decision['error']}"
            state.final_message = msg
            return EngineTurnResult(ok=False, reply=msg, action="", state=state, tool="", capability_id=cap)

        llm_tool = str(decision.get("tool") or "").strip()
        llm_params = dict(decision.get("params") or {})
        llm_reply = str(decision.get("reply") or "").strip()
        state.extensions["agent_llm"] = {
            "provider": decision.get("provider"),
            "tool": llm_tool,
        }

        if llm_tool in _GENERATE_CAPS:
            action = "refine" if llm_tool == "refine_bot" else "generate"
            return EngineTurnResult(
                ok=True,
                reply=llm_reply,
                action=action,
                state=state,
                tool=llm_tool,
                capability_id=llm_tool,
                generate_request=text,
                user_data_updates={
                    "force_generate_once": True,
                    "translated_source": "engine_turn_llm",
                    "last_bot_request": text[:2000],
                    "multi_agent_state_id": state.state_id,
                },
            )

        if llm_tool:
            tool = llm_tool
            cap = llm_tool
            params = dict(llm_params)
            params.setdefault("text", text)
            params.setdefault("raw_text", text)
            if repo_path:
                params.setdefault("path", repo_path)
            state.capability_id = tool
            state.user_intent = tool
            # fall through to execute_tool_gated below
        else:
            # Agent answered without a tool — still agent brain, not static menu
            if not llm_reply:
                llm_reply = "لم أستطع تحديد إجراء. اكتب الطلب بشكل أوضح (توليد بوت / سحب مستودع / استضافة)."
            state.final_message = llm_reply
            try:
                state.transition(AgentStatus.DELIVERED, role=AgentRole.ROUTER, force=True)
            except Exception:
                state.status = AgentStatus.DELIVERED.value
            return EngineTurnResult(
                ok=True,
                reply=llm_reply[:4000],
                action="agent_reply",
                state=state,
                tool="",
                capability_id=cap or "agent_llm",
            )

    # 5) Host / git / repo tools → execute_tool_gated (HITL when required)
    state.route_params = params
    state.capability_id = cap or tool
    try:
        # Pass user_data into extensions for tools that need active_repo
        state.extensions = dict(state.extensions or {})
        state.extensions["user_data"] = ud
        state = execute_tool_gated(state, tool, params)
    except Exception as exc:
        logger.exception("execute_tool_gated failed tool=%s", tool)
        return EngineTurnResult(
            ok=False,
            reply=f"فشل تنفيذ `{tool}`: {type(exc).__name__}",
            action="tool",
            state=state,
            tool=tool,
            capability_id=cap,
        )

    # HITL pause
    status_u = str(getattr(state, "status", "") or "").upper()
    pending = (state.extensions or {}).get("pending_action") or {}
    if status_u in {"AWAITING_CONFIRMATION", "WAITING_CONFIRM"} or (
        isinstance(pending, dict) and pending.get("action_id")
    ):
        msg = (state.final_message or "").strip() or (
            f"يتطلب تأكيد لتنفيذ `{tool}`. اكتب: تأكيد أو رفض."
        )
        updates: dict[str, Any] = {
            "multi_agent_state_id": state.state_id,
            "multi_agent_pending": {
                "action_id": pending.get("action_id"),
                "state_id": state.state_id,
                "tool": tool,
                "confirm_token": pending.get("confirm_token"),
            },
        }
        return EngineTurnResult(
            ok=True,
            reply=msg[:4000],
            action="awaiting_confirm",
            state=state,
            tool=tool,
            capability_id=cap,
            needs_confirmation=True,
            user_data_updates=updates,
        )

    tr = (state.extensions or {}).get("tool_result") or {}
    reply = (state.final_message or "").strip() or str(tr.get("message") or "")
    ok = bool(tr.get("ok", True)) if tr else bool(reply)

    updates = {"multi_agent_state_id": state.state_id}
    # Propagate active_repo if tool data includes path
    data = tr.get("data") if isinstance(tr, dict) else None
    if isinstance(data, dict) and data.get("path"):
        updates["active_repo"] = {
            "path": data["path"],
            "url": data.get("url") or "",
        }
        updates["last_project_path"] = data["path"]

    # repo_modify → refine via multi-agent (structural change owned by agents)
    if isinstance(tr, dict) and (tr.get("data") or {}).get("defer_refine"):
        change = str((tr.get("data") or {}).get("change") or text)
        path = str((tr.get("data") or {}).get("path") or repo_path or "")
        gen = f"تعديل البوت/المشروع في {path}: {change}" if path else change
        return EngineTurnResult(
            ok=True,
            reply=(reply or tr.get("message") or "جاري التعديل عبر المحرك…")[:4000],
            action="refine",
            state=state,
            tool=tool,
            capability_id=cap or "repo_modify",
            generate_request=gen,
            user_data_updates={
                **updates,
                "force_generate_once": True,
                "translated_source": "engine_turn_repo_modify",
                "last_bot_request": gen[:2000],
                "last_project_path": path or updates.get("last_project_path", ""),
            },
        )

    # Deferred generate signal from tool layer
    if isinstance(tr, dict) and tr.get("defer") and tool in _GENERATE_CAPS:
        return EngineTurnResult(
            ok=True,
            reply=reply,
            action="generate" if tool == "generate_bot" else "refine",
            state=state,
            tool=tool,
            capability_id=cap,
            generate_request=text,
            user_data_updates={
                **updates,
                "force_generate_once": True,
                "translated_source": "engine_turn",
                "last_bot_request": text[:2000],
            },
        )

    if not reply:
        reply = f"تم تنفيذ `{tool}`." if ok else f"فشل تنفيذ `{tool}`."

    return EngineTurnResult(
        ok=ok,
        reply=reply[:4000],
        action="tool",
        state=state,
        tool=tool,
        capability_id=cap,
        user_data_updates=updates,
    )


__all__ = ["EngineTurnResult", "handle_user_turn"]
