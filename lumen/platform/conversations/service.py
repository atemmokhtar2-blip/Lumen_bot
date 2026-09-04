"""Conversation service — multi-thread chat like WhatsApp/ChatGPT."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .store import ConversationStore, get_conversation_store
from .types import Conversation, Message

logger = logging.getLogger(__name__)

_WINDOW_MESSAGES = int(os.getenv("LUMEN_CONV_WINDOW_MESSAGES") or "20")
_WINDOW_CHARS = int(os.getenv("LUMEN_CONV_WINDOW_CHARS") or "12000")  # ~4k tokens
_SUMMARY_AFTER = int(os.getenv("LUMEN_CONV_SUMMARY_AFTER") or "20")


class ConversationService:
    def __init__(self, store: ConversationStore | None = None) -> None:
        self._store = store or get_conversation_store()

    def ensure_active(self, user_id: int, *, conversation_id: str | None = None) -> Conversation:
        """Return selected conversation or last active; create if none."""
        uid = int(user_id)
        if conversation_id:
            c = self._store.get_conversation(str(conversation_id), user_id=uid)
            if c and c.is_active:
                return c
        rows = self._store.list_conversations(uid, limit=1, active_only=True)
        if rows:
            return rows[0]
        return self._store.create_conversation(uid, title="محادثة جديدة")

    def new_conversation(self, user_id: int, *, title: str = "") -> Conversation:
        return self._store.create_conversation(int(user_id), title=title or "محادثة جديدة")

    def list_for_user(self, user_id: int, *, limit: int = 20) -> list[Conversation]:
        return self._store.list_conversations(int(user_id), limit=limit, active_only=True)

    def archive(self, user_id: int, conversation_id: str) -> bool:
        return self._store.archive_conversation(str(conversation_id), user_id=int(user_id))

    def append(
        self,
        user_id: int,
        conversation_id: str,
        *,
        role: str,
        content: str,
        tokens: int = 0,
        metadata: dict | None = None,
    ) -> Message:
        # Defense: never persist Telegram bot tokens in conversation history
        try:
            from lumen.bot.helpers import looks_like_bot_token
            if looks_like_bot_token(content or ""):
                content = "[redacted_bot_token]"
        except Exception:
            if content and ":" in content and len(content) > 40 and content.split(":", 1)[0].isdigit():
                content = "[redacted_bot_token]"
        if not tokens and content:
            tokens = max(1, len(content) // 4)
        msg = self._store.append_message(
            str(conversation_id),
            user_id=int(user_id),
            role=role,
            content=content,
            tokens=tokens,
            metadata=metadata,
        )
        # Lightweight rolling summary when long
        try:
            c = self._store.get_conversation(str(conversation_id), user_id=int(user_id))
            if c and c.message_count >= _SUMMARY_AFTER and c.message_count % 5 == 0:
                self._maybe_summarize(int(user_id), str(conversation_id), c)
        except Exception:
            logger.debug("conversation summarize soft-fail", exc_info=True)
        return msg

    def _maybe_summarize(self, user_id: int, conversation_id: str, conv: Conversation) -> None:
        # Extractive summary without LLM (cheap, deterministic)
        msgs = self._store.list_messages(conversation_id, user_id=user_id, limit=40)
        older = msgs[:-_WINDOW_MESSAGES] if len(msgs) > _WINDOW_MESSAGES else []
        if not older:
            return
        bits = []
        for m in older[-12:]:
            prefix = "المستخدم" if m.role == "user" else "المساعد"
            bits.append(f"{prefix}: {(m.content or '')[:120]}")
        summary = (conv.summary + "\n" if conv.summary else "") + " | ".join(bits)
        summary = summary[-2000:]
        self._store.touch_conversation(conversation_id, summary=summary)

    def context_for_llm(self, user_id: int, conversation_id: str) -> dict[str, Any]:
        """Sliding window: last N messages + summary, capped by chars."""
        uid = int(user_id)
        conv = self._store.get_conversation(str(conversation_id), user_id=uid)
        if not conv:
            return {"conversation_id": "", "summary": "", "messages": [], "title": ""}
        msgs = self._store.list_messages(str(conversation_id), user_id=uid, limit=_WINDOW_MESSAGES * 2)
        # char budget from the end
        selected: list[Message] = []
        chars = 0
        for m in reversed(msgs):
            piece = len(m.content or "")
            if selected and (len(selected) >= _WINDOW_MESSAGES or chars + piece > _WINDOW_CHARS):
                break
            selected.append(m)
            chars += piece
        selected.reverse()
        return {
            "conversation_id": conv.id,
            "title": conv.title,
            "summary": conv.summary or "",
            "messages": [
                {"role": m.role, "content": m.content, "tokens": m.tokens, "ts": m.created_at}
                for m in selected
            ],
            "message_count": conv.message_count,
        }

    def search(self, user_id: int, query: str, *, limit: int = 20) -> list[Message]:
        return self._store.search_messages(int(user_id), query, limit=limit)

    def purge_expired(self, *, days: int = 30) -> int:
        return int(self._store.purge_older_than(days=days) or 0)

    def export_json(self, user_id: int, conversation_id: str) -> dict[str, Any]:

        conv = self._store.get_conversation(str(conversation_id), user_id=int(user_id))
        if not conv:
            return {"ok": False, "error": "not_found"}
        msgs = self._store.list_messages(str(conversation_id), user_id=int(user_id), limit=500)
        return {
            "ok": True,
            "conversation": conv.public_dict(),
            "messages": [m.public_dict() for m in msgs],
        }


_SVC: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    global _SVC
    if _SVC is None:
        _SVC = ConversationService()
    return _SVC


def reset_conversation_service_for_tests() -> None:
    global _SVC
    _SVC = None
    from .store import reset_conversation_store_for_tests
    reset_conversation_store_for_tests()
