"""Official python-telegram-bot BasePersistence backed by Redis.

Wires user_data into Application so PTB itself:
  - loads all sessions on startup (get_user_data)
  - refreshes each user from Redis before every handler (refresh_user_data)
  - writes after every handled update (update_user_data)
  - flushes on shutdown

This is the framework-native path (see PTB wiki «Making your bot persistent»).
Manual SessionStore hydrate/save remains as a secondary immediate-write path for
critical mid-handler persists (e.g. engine_ui after a button).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from copy import deepcopy
from typing import Any, DefaultDict, Dict, Optional, Tuple

from telegram.ext import BasePersistence, PersistenceInput

from lumen.bot.session_store import (
    SessionStore,
    _DURABLE_KEYS,
    get_session_store,
)

logger = logging.getLogger("lumen.bot.ptb_redis_persistence")

# Type aliases matching PTB generics
UD = Dict[str, Any]
CD = Dict[str, Any]
BD = Dict[str, Any]
CDCData = Tuple[list, Dict[str, str]]
ConversationDict = Dict[Any, Any]


class RedisPersistence(BasePersistence[UD, CD, BD]):
    """Redis-backed PTB persistence — multi-worker / restart safe user context."""

    def __init__(
        self,
        store: SessionStore | None = None,
        *,
        update_interval: float = 5.0,
        store_user_data: bool = True,
        store_chat_data: bool = False,
        store_bot_data: bool = False,
        store_callback_data: bool = False,
    ) -> None:
        store_data = PersistenceInput(
            user_data=store_user_data,
            chat_data=store_chat_data,
            bot_data=store_bot_data,
            callback_data=store_callback_data,
        )
        super().__init__(store_data=store_data, update_interval=float(update_interval))
        self._store = store  # lazy via get_session_store if None
        self._chat: Dict[int, CD] = {}
        self._bot: BD = {}
        self._conversations: Dict[str, ConversationDict] = {}
        self._callback_data: Optional[CDCData] = None

    def _ss(self) -> SessionStore:
        if self._store is not None:
            return self._store
        return get_session_store()

    # ── load (startup) ─────────────────────────────────────────────────────

    async def get_user_data(self) -> DefaultDict[int, UD]:
        """Load every known user session from Redis into Application.user_data."""
        out: DefaultDict[int, UD] = defaultdict(dict)
        try:
            for uid in self._ss().list_user_ids():
                data = self._ss().load(uid)
                if data:
                    out[int(uid)] = dict(data)
        except Exception as exc:
            logger.warning(
                "get_user_data failed: %s:%s", type(exc).__name__, str(exc)[:120]
            )
        logger.info("persistence get_user_data loaded=%s users", len(out))
        return out

    async def get_chat_data(self) -> DefaultDict[int, CD]:
        return defaultdict(dict)

    async def get_bot_data(self) -> BD:
        return dict(self._bot)

    async def get_callback_data(self) -> Optional[CDCData]:
        return self._callback_data

    async def get_conversations(self, name: str) -> ConversationDict:
        return dict(self._conversations.get(name) or {})

    # ── refresh (before every handler — multi-worker source of truth) ──────

    async def refresh_user_data(self, user_id: int, user_data: UD) -> None:
        """Overwrite durable keys from Redis in-place before the handler runs."""
        try:
            saved = self._ss().load(int(user_id))
        except Exception as exc:
            logger.warning(
                "refresh_user_data load failed uid=%s: %s",
                user_id, type(exc).__name__,
            )
            return
        if not saved:
            return
        for k, v in saved.items():
            if k in _DURABLE_KEYS:
                user_data[k] = deepcopy(v) if isinstance(v, (dict, list)) else v

    async def refresh_chat_data(self, chat_id: int, chat_data: CD) -> None:
        return

    async def refresh_bot_data(self, bot_data: BD) -> None:
        return

    # ── update (after every handled update) ────────────────────────────────

    async def update_user_data(self, user_id: int, data: UD) -> None:
        if not data:
            return
        try:
            self._ss().save(int(user_id), dict(data))
        except Exception as exc:
            logger.error(
                "update_user_data failed uid=%s: %s:%s",
                user_id, type(exc).__name__, str(exc)[:160],
            )

    async def update_chat_data(self, chat_id: int, data: CD) -> None:
        self._chat[int(chat_id)] = dict(data or {})

    async def update_bot_data(self, data: BD) -> None:
        self._bot = dict(data or {})

    async def update_callback_data(self, data: CDCData) -> None:
        self._callback_data = data

    async def update_conversation(
        self, name: str, key: Tuple[Any, ...], new_state: Optional[object]
    ) -> None:
        conv = self._conversations.setdefault(name, {})
        if new_state is None:
            conv.pop(key, None)
        else:
            conv[key] = new_state

    async def drop_user_data(self, user_id: int) -> None:
        try:
            self._ss().clear(int(user_id))
        except Exception:
            logger.exception("drop_user_data failed uid=%s", user_id)

    async def drop_chat_data(self, chat_id: int) -> None:
        self._chat.pop(int(chat_id), None)

    async def flush(self) -> None:
        """No-op: each update_user_data already writes through to Redis."""
        logger.debug("persistence flush (redis write-through, nothing buffered)")
