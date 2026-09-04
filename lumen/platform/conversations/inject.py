"""Inject conversation history into agent/LLM message lists."""
from __future__ import annotations

import os
from typing import Any


def conversation_messages_for_user(
    user_id: int,
    *,
    conversation_id: str = "",
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> list[dict[str, str]]:
    """Return role/content dicts suitable for agent_brain.decide messages."""
    uid = int(user_id or 0)
    if not uid:
        return []
    try:
        max_m = int(max_messages or os.getenv("LUMEN_CONV_WINDOW_MESSAGES") or "20")
    except ValueError:
        max_m = 20
    try:
        max_c = int(max_chars or os.getenv("LUMEN_CONV_WINDOW_CHARS") or "12000")
    except ValueError:
        max_c = 12000
    try:
        from lumen.platform.conversations import get_conversation_service

        svc = get_conversation_service()
        conv = svc.ensure_active(uid, conversation_id=conversation_id or None)
        ctx = svc.context_for_llm(uid, conv.id)
    except Exception:
        return []
    out: list[dict[str, str]] = []
    chars = 0
    summary = (ctx.get("summary") or "").strip()
    out.append({"role": "system", "content": "CONVERSATION HISTORY (durable thread):"})
    chars += 40
    if summary:
        piece = summary[:1500]
        out.append({"role": "system", "content": f"CONVERSATION SUMMARY: {piece}"})
        chars += len(piece)
    for m in ctx.get("messages") or []:
        role = str(m.get("role") or "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        content = str(m.get("content") or "")[:800]
        if not content:
            continue
        if len(out) >= max_m + 1 or chars + len(content) > max_c:
            break
        out.append({"role": role, "content": content})
        chars += len(content)
    return out


def merge_history_into_messages(
    messages: list[dict[str, Any]],
    *,
    user_id: int = 0,
    conversation_id: str = "",
) -> list[dict[str, Any]]:
    """Prepend conversation history after the first system message (if any)."""
    hist = conversation_messages_for_user(user_id, conversation_id=conversation_id)
    if not hist:
        return list(messages or [])
    base = list(messages or [])
    # Avoid double-inject if already present
    for m in base:
        if "CONVERSATION SUMMARY" in str(m.get("content") or "") or "CONVERSATION HISTORY" in str(
            m.get("content") or ""
        ):
            return base
    if base and str(base[0].get("role") or "") == "system":
        return [base[0]] + hist + base[1:]
    return hist + base


__all__ = ["conversation_messages_for_user", "merge_history_into_messages"]
