"""Actionable Telegram errors — every failure offers a next step.

Instead of dead-end text, attach an InlineKeyboard that opens the correct
pending flow (GitHub PAT, bot token, retry clone, etc.).
"""
from __future__ import annotations

import logging
from typing import Any

from lumen.engine.services.ui_state.models import UiButton

from .keyboards import build_inline_keyboard
from .rtl_text import code_path, code_url

logger = logging.getLogger("lumen_bot.ui.actionable_errors")


def private_clone_error(
    *,
    url: str = "",
    detail: str = "",
    user_id: int = 0,
) -> tuple[str, Any]:
    """Fail closed message + button that arms pending_clone_auth on press."""
    lines = ["❌ فشل سحب المستودع: المستودع خاص أو يتطلب مصادقة."]
    if url:
        lines.append(f"• الرابط: {code_url(url)}")
    if detail:
        lines.append(f"• التفاصيل: {detail[:200]}")
    lines.append("")
    lines.append("اضغط الزر لإرسال توكن GitHub (PAT) بصلاحية `repo`.")
    text = "\n".join(lines)
    buttons = (
        (UiButton("🔑 إرسال توكن GitHub الآن", "ask_gh_token", "clone", style="success"),),
        (UiButton("🏠 الرئيسية", "home", style="primary"),),
    )
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return text, markup


def create_repo_error(
    *,
    name: str = "",
    detail: str = "",
    user_id: int = 0,
) -> tuple[str, Any]:
    lines = ["❌ فشل إنشاء المستودع على GitHub."]
    if name:
        lines.append(f"• الاسم: `{name}`")
    if detail:
        lines.append(f"• السبب: {detail[:240]}")
    lines.append("")
    lines.append("أرسل PAT بصلاحية `repo` أو اضغط الزر.")
    text = "\n".join(lines)
    buttons = (
        (UiButton("🔑 إرسال توكن GitHub", "ask_gh_token", "create", style="success"),),
        (UiButton("🏠 الرئيسية", "home", style="primary"),),
    )
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return text, markup


def host_error(
    *,
    detail: str = "",
    project_path: str = "",
    user_id: int = 0,
) -> tuple[str, Any]:
    lines = ["❌ فشل بدء الاستضافة."]
    if project_path:
        lines.append(f"• المشروع: {code_path(project_path)}")
    if detail:
        lines.append(f"• السبب: {detail[:280]}")
    lines.append("")
    lines.append("تحقق من التوكن والعزل ثم أعد المحاولة.")
    text = "\n".join(lines)
    buttons = (
        (UiButton("🚀 إعادة طلب التوكن", "ask_bot_token", "host", style="success"),),
        (UiButton("🩺 تشخيص", "dash_diagnose", "0", style="primary"),),
        (UiButton("🏠 الرئيسية", "home"),),
    )
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return text, markup


def generic_fail(
    *,
    title: str,
    detail: str = "",
    user_id: int = 0,
) -> tuple[str, Any]:
    lines = [f"❌ {title}"]
    if detail:
        lines.append(detail[:400])
    text = "\n".join(lines)
    buttons = ((UiButton("🏠 الرئيسية", "home", style="primary"),),)
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return text, markup


def needs_auth_prompt(
    *,
    url: str = "",
    op: str = "clone",
    user_id: int = 0,
) -> tuple[str, Any]:
    """Private-repo auth required — always include GitHub token button."""
    lines = ["🔒 المستودع خاص ويحتاج مصادقة."]
    if url:
        from .rtl_text import code_url
        lines.append(f"• الرابط: {code_url(url)}")
    lines.append("")
    lines.append("أرسل PAT بصلاحية `repo` أو اضغط الزر أدناه.")
    text = "\n".join(lines)
    arg = "create" if op == "create" else "clone"
    buttons = (
        (UiButton("🔑 إرسال توكن GitHub الآن", "ask_gh_token", arg, style="success"),),
        (UiButton("🔐 فتح اللوحة الآمنة", "ask_gh_token", arg, style="primary"),),
        (UiButton("🏠 الرئيسية", "home"),),
    )
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return text, markup


def git_op_error(
    *,
    op: str = "clone",
    detail: str = "",
    user_id: int = 0,
) -> tuple[str, Any]:
    titles = {
        "clone": "فشل سحب المستودع",
        "pull": "فشل سحب التحديثات",
        "push": "فشل الدفع إلى GitHub",
        "create": "فشل إنشاء المستودع",
    }
    title = titles.get(op, "فشلت عملية Git")
    lines = [f"❌ {title}"]
    if detail:
        lines.append(f"• السبب: {detail[:280]}")
    lines.append("")
    if op in {"clone", "pull", "create"}:
        lines.append("إذا كان المستودع خاصاً أرسل PAT، أو أعد المحاولة.")
        btn = (UiButton("🔑 إرسال توكن GitHub", "ask_gh_token", "clone" if op != "create" else "create", style="success"),)
    else:
        lines.append("تحقق من الصلاحيات ثم أعد المحاولة.")
        btn = (UiButton("🔑 إرسال توكن GitHub", "ask_gh_token", "clone", style="success"),)
    buttons = (btn, (UiButton("🏠 الرئيسية", "home"),))
    markup = build_inline_keyboard(buttons, user_id=int(user_id or 0))
    return "\n".join(lines), markup


async def send_actionable_error(
    target: Any,
    *,
    kind: str,
    user_id: int = 0,
    detail: str = "",
    url: str = "",
    name: str = "",
    project_path: str = "",
    title: str = "",
) -> None:
    """Edit/reply with actionable error. Never raises to caller for UX failures."""
    kind = (kind or "generic").strip().lower()
    try:
        if kind in {"clone", "private", "auth"}:
            text, markup = private_clone_error(url=url, detail=detail, user_id=user_id)
        elif kind == "create":
            text, markup = create_repo_error(name=name, detail=detail, user_id=user_id)
        elif kind in {"host", "live"}:
            text, markup = host_error(detail=detail, project_path=project_path, user_id=user_id)
        elif kind in {"pull", "push", "git"}:
            text, markup = git_op_error(op=kind if kind in {"pull", "push"} else "clone", detail=detail, user_id=user_id)
        elif kind == "needs_auth":
            text, markup = needs_auth_prompt(url=url, op="clone", user_id=user_id)
        else:
            text, markup = generic_fail(title=title or "فشلت العملية", detail=detail, user_id=user_id)
    except Exception:
        logger.exception("build actionable error failed kind=%s", kind)
        text, markup = f"❌ {title or kind}: {detail}"[:500], None

    try:
        if hasattr(target, "edit_text"):
            await target.edit_text(text, reply_markup=markup)
        else:
            await target.reply_text(text, reply_markup=markup)
    except Exception:
        try:
            if hasattr(target, "edit_text"):
                await target.edit_text(text[:4000])
            else:
                await target.reply_text(text[:4000])
        except Exception:
            logger.exception("send_actionable_error delivery failed")
