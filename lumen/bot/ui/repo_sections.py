"""Paginated repo-understanding UI — short header + section buttons.

Avoids dumping multi-kilobyte blocks into a single Telegram message.
Sections live in user_data['repo_sections'] and are revealed via signed
callbacks (repo_sec).
"""
from __future__ import annotations

import logging
from typing import Any

from lumen.engine.services.ui_state.models import UiButton

from .keyboards import build_inline_keyboard
from .rtl_text import code_path, code_url

logger = logging.getLogger("lumen_bot.ui.repo_sections")

_MAX_SECTION = 3500


def _clip(text: str, limit: int = _MAX_SECTION) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 20] + "\n…(مختصر)"


def build_sections_from_contract(repo_contract: Any, *, path: str = "", url: str = "") -> dict[str, str]:
    """Split understand_repo output into named sections for pagination."""
    sections: dict[str, str] = {}
    try:
        summary = ""
        if hasattr(repo_contract, "to_user_summary"):
            summary = str(repo_contract.to_user_summary() or "")
        elif isinstance(repo_contract, dict):
            summary = str(repo_contract.get("summary") or repo_contract)
        else:
            summary = str(repo_contract)
        sections["summary"] = _clip(summary, 3200)
    except Exception:
        sections["summary"] = "لا يتوفر ملخص."

    # Entry points
    try:
        entries = list(getattr(repo_contract, "entry_points", None) or [])
        if entries:
            lines = ["📂 نقاط الدخول:"]
            for ep in entries[:12]:
                p = getattr(ep, "path", None) or (ep.get("path") if isinstance(ep, dict) else str(ep))
                lines.append(f"• {code_path(str(p))}")
            sections["entries"] = "\n".join(lines)
        else:
            sections["entries"] = "لا نقاط دخول مكتشفة."
    except Exception:
        sections["entries"] = "تعذّر استخراج نقاط الدخول."

    # Dependencies / frameworks
    try:
        deps = list(getattr(repo_contract, "dependencies", None) or [])
        fws = list(getattr(repo_contract, "frameworks", None) or [])
        lines = ["⚙️ التبعيات والأُطر:"]
        if fws:
            lines.append("أطر: " + ", ".join(str(x) for x in fws[:15]))
        if deps:
            lines.append("حزم:")
            for d in deps[:25]:
                lines.append(f"• `{d}`")
        if len(lines) == 1:
            lines.append("لا تبعيات مكتشفة.")
        sections["deps"] = _clip("\n".join(lines))
    except Exception:
        sections["deps"] = "تعذّر استخراج التبعيات."

    # Meta header fields
    header_bits = ["✅ تم فهم المستودع"]
    if url:
        header_bits.append(f"• الرابط: {code_url(url)}")
    if path:
        header_bits.append(f"• المسار: {code_path(path)}")
    try:
        style = str(getattr(repo_contract, "architecture_style", "") or "")
        if style:
            header_bits.append(f"• النمط: `{style}`")
        is_bot = bool(getattr(repo_contract, "is_telegram_bot", False))
        header_bits.append("• بوت تيليجرام: " + ("نعم" if is_bot else "لا"))
    except Exception:
        pass
    sections["header"] = "\n".join(header_bits)
    return sections


def section_keyboard(*, user_id: int, show_run: bool = False) -> Any:
    rows = [
        (
            UiButton("📄 الملخص", "repo_sec", "summary", style="primary"),
            UiButton("📂 نقاط الدخول", "repo_sec", "entries", style="primary"),
        ),
        (
            UiButton("⚙️ التبعيات", "repo_sec", "deps", style="primary"),
            UiButton("↩️ الرأس", "repo_sec", "header"),
        ),
    ]
    if show_run:
        rows.append((UiButton("🚀 تشغيل / استضافة", "ask_bot_token", "run", style="success"),))
    rows.append((UiButton("🏠 الرئيسية", "home"),))
    return build_inline_keyboard(tuple(rows), user_id=int(user_id or 0))


def store_sections(user_data: dict, sections: dict[str, str]) -> None:
    if not isinstance(user_data, dict):
        return
    # Keep only small string values
    clean = {str(k)[:24]: str(v)[:_MAX_SECTION] for k, v in (sections or {}).items()}
    user_data["repo_sections"] = clean


def get_section(user_data: dict | None, key: str) -> str:
    if not isinstance(user_data, dict):
        return "لا بيانات."
    secs = user_data.get("repo_sections") or {}
    if not isinstance(secs, dict):
        return "لا بيانات."
    val = secs.get(key) or secs.get("header") or "القسم غير متاح."
    return str(val)[:_MAX_SECTION]
