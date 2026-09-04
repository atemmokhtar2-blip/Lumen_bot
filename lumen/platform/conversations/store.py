"""Conversation + message persistence (memory + optional Postgres)."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Optional, Protocol

from .types import Conversation, Message

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lumen_conversations (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    summary TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_lumen_conv_user ON lumen_conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS lumen_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES lumen_conversations(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    created_at DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_lumen_msg_conv ON lumen_messages (conversation_id, created_at DESC);
"""


class ConversationStore(Protocol):
    def create_conversation(self, user_id: int, *, title: str = "") -> Conversation: ...
    def get_conversation(self, conversation_id: str, *, user_id: int) -> Optional[Conversation]: ...
    def list_conversations(self, user_id: int, *, limit: int = 30, active_only: bool = True) -> list[Conversation]: ...
    def touch_conversation(self, conversation_id: str, *, title: str | None = None, summary: str | None = None) -> None: ...
    def archive_conversation(self, conversation_id: str, *, user_id: int) -> bool: ...
    def append_message(
        self,
        conversation_id: str,
        *,
        user_id: int,
        role: str,
        content: str,
        tokens: int = 0,
        metadata: dict | None = None,
    ) -> Message: ...
    def list_messages(self, conversation_id: str, *, user_id: int, limit: int = 30) -> list[Message]: ...
    def purge_older_than(self, days: int = 30) -> int: ...
    def search_messages(self, user_id: int, query: str, *, limit: int = 20) -> list[Message]: ...


class MemoryConversationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._convs: dict[str, Conversation] = {}
        self._msgs: dict[str, list[Message]] = {}  # conv_id -> messages chronological

    def create_conversation(self, user_id: int, *, title: str = "") -> Conversation:
        now = time.time()
        cid = uuid.uuid4().hex
        c = Conversation(
            id=cid,
            user_id=int(user_id),
            title=(title or "محادثة جديدة")[:120],
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        with self._lock:
            self._convs[cid] = c
            self._msgs[cid] = []
        return c

    def get_conversation(self, conversation_id: str, *, user_id: int) -> Optional[Conversation]:
        with self._lock:
            c = self._convs.get(str(conversation_id))
            if not c or int(c.user_id) != int(user_id):
                return None
            return c

    def list_conversations(self, user_id: int, *, limit: int = 30, active_only: bool = True) -> list[Conversation]:
        with self._lock:
            rows = [c for c in self._convs.values() if int(c.user_id) == int(user_id)]
            if active_only:
                rows = [c for c in rows if c.is_active]
            rows.sort(key=lambda x: x.updated_at, reverse=True)
            return rows[: int(limit)]

    def touch_conversation(self, conversation_id: str, *, title: str | None = None, summary: str | None = None) -> None:
        with self._lock:
            c = self._convs.get(str(conversation_id))
            if not c:
                return
            c.updated_at = time.time()
            if title is not None and title.strip():
                c.title = title.strip()[:120]
            if summary is not None:
                c.summary = (summary or "")[:4000]

    def archive_conversation(self, conversation_id: str, *, user_id: int) -> bool:
        with self._lock:
            c = self._convs.get(str(conversation_id))
            if not c or int(c.user_id) != int(user_id):
                return False
            c.is_active = False
            c.updated_at = time.time()
            return True

    def append_message(
        self,
        conversation_id: str,
        *,
        user_id: int,
        role: str,
        content: str,
        tokens: int = 0,
        metadata: dict | None = None,
    ) -> Message:
        role_n = (role or "user").strip().lower()
        if role_n not in {"user", "assistant", "system"}:
            role_n = "user"
        with self._lock:
            c = self._convs.get(str(conversation_id))
            if not c or int(c.user_id) != int(user_id):
                raise PermissionError("conversation_not_found")
            mid = uuid.uuid4().hex
            msg = Message(
                id=mid,
                conversation_id=str(conversation_id),
                user_id=int(user_id),
                role=role_n,
                content=(content or "")[:8000],
                tokens=max(0, int(tokens or 0)),
                created_at=time.time(),
                metadata=dict(metadata or {}),
            )
            self._msgs.setdefault(str(conversation_id), []).append(msg)
            c.message_count = len(self._msgs[str(conversation_id)])
            c.updated_at = time.time()
            # auto title from first user message
            if c.message_count <= 2 and role_n == "user" and (not c.title or c.title == "محادثة جديدة"):
                c.title = (content or "").strip().replace("\n", " ")[:60] or c.title
            return msg

    def list_messages(self, conversation_id: str, *, user_id: int, limit: int = 30) -> list[Message]:
        with self._lock:
            c = self._convs.get(str(conversation_id))
            if not c or int(c.user_id) != int(user_id):
                return []
            rows = list(self._msgs.get(str(conversation_id), []))
            if limit > 0:
                rows = rows[-int(limit) :]
            return rows


    def search_messages(self, user_id: int, query: str, *, limit: int = 20) -> list[Message]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: list[Message] = []
        with self._lock:
            for cid, msgs in self._msgs.items():
                c = self._convs.get(cid)
                if not c or int(c.user_id) != int(user_id):
                    continue
                for m in reversed(msgs):
                    if q in (m.content or "").lower():
                        hits.append(m)
                        if len(hits) >= int(limit):
                            return hits
        return hits

    def purge_older_than(self, days: int = 30) -> int:
        cutoff = time.time() - max(1, int(days)) * 86400
        removed = 0
        with self._lock:
            dead = [cid for cid, c in self._convs.items() if c.updated_at < cutoff]
            for cid in dead:
                self._convs.pop(cid, None)
                self._msgs.pop(cid, None)
                removed += 1
        return removed


class PostgresConversationStore:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self._dict_row = dict_row
        self.dsn = dsn
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def create_conversation(self, user_id: int, *, title: str = "") -> Conversation:
        now = time.time()
        cid = uuid.uuid4().hex
        title_s = (title or "محادثة جديدة")[:120]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO lumen_conversations
                    (id, user_id, title, created_at, updated_at, is_active, summary, message_count, metadata)
                VALUES (%s,%s,%s,%s,%s,TRUE,'',0,'{}'::jsonb)
                """,
                (cid, int(user_id), title_s, now, now),
            )
            conn.commit()
        return Conversation(id=cid, user_id=int(user_id), title=title_s, created_at=now, updated_at=now)

    def get_conversation(self, conversation_id: str, *, user_id: int) -> Optional[Conversation]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM lumen_conversations WHERE id=%s AND user_id=%s",
                (str(conversation_id), int(user_id)),
            ).fetchone()
        return self._row_conv(row) if row else None

    def list_conversations(self, user_id: int, *, limit: int = 30, active_only: bool = True) -> list[Conversation]:
        q = "SELECT * FROM lumen_conversations WHERE user_id=%s"
        params: list[Any] = [int(user_id)]
        if active_only:
            q += " AND is_active=TRUE"
        q += " ORDER BY updated_at DESC LIMIT %s"
        params.append(int(limit))
        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_conv(r) for r in rows if r]

    def touch_conversation(self, conversation_id: str, *, title: str | None = None, summary: str | None = None) -> None:
        sets = ["updated_at=%s"]
        params: list[Any] = [time.time()]
        if title is not None and title.strip():
            sets.append("title=%s")
            params.append(title.strip()[:120])
        if summary is not None:
            sets.append("summary=%s")
            params.append((summary or "")[:4000])
        params.append(str(conversation_id))
        with self._conn() as conn:
            conn.execute(f"UPDATE lumen_conversations SET {', '.join(sets)} WHERE id=%s", params)
            conn.commit()

    def archive_conversation(self, conversation_id: str, *, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE lumen_conversations SET is_active=FALSE, updated_at=%s WHERE id=%s AND user_id=%s",
                (time.time(), str(conversation_id), int(user_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    def append_message(
        self,
        conversation_id: str,
        *,
        user_id: int,
        role: str,
        content: str,
        tokens: int = 0,
        metadata: dict | None = None,
    ) -> Message:
        role_n = (role or "user").strip().lower()
        if role_n not in {"user", "assistant", "system"}:
            role_n = "user"
        mid = uuid.uuid4().hex
        now = time.time()
        meta = json.dumps(metadata or {}, ensure_ascii=False)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, message_count FROM lumen_conversations WHERE id=%s AND user_id=%s",
                (str(conversation_id), int(user_id)),
            ).fetchone()
            if not row:
                raise PermissionError("conversation_not_found")
            conn.execute(
                """
                INSERT INTO lumen_messages (id, conversation_id, user_id, role, content, tokens, created_at, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,
                (mid, str(conversation_id), int(user_id), role_n, (content or "")[:8000], int(tokens or 0), now, meta),
            )
            new_count = int(row["message_count"] or 0) + 1
            title = row["title"] or "محادثة جديدة"
            if new_count <= 2 and role_n == "user" and (not title or title == "محادثة جديدة"):
                title = (content or "").strip().replace("\n", " ")[:60] or title
            conn.execute(
                "UPDATE lumen_conversations SET message_count=%s, updated_at=%s, title=%s WHERE id=%s",
                (new_count, now, title, str(conversation_id)),
            )
            conn.commit()
        return Message(
            id=mid,
            conversation_id=str(conversation_id),
            user_id=int(user_id),
            role=role_n,
            content=(content or "")[:8000],
            tokens=int(tokens or 0),
            created_at=now,
            metadata=dict(metadata or {}),
        )

    def list_messages(self, conversation_id: str, *, user_id: int, limit: int = 30) -> list[Message]:
        with self._conn() as conn:
            own = conn.execute(
                "SELECT 1 FROM lumen_conversations WHERE id=%s AND user_id=%s",
                (str(conversation_id), int(user_id)),
            ).fetchone()
            if not own:
                return []
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM lumen_messages WHERE conversation_id=%s
                    ORDER BY created_at DESC LIMIT %s
                ) t ORDER BY created_at ASC
                """,
                (str(conversation_id), int(limit)),
            ).fetchall()
        return [self._row_msg(r) for r in rows if r]


    def search_messages(self, user_id: int, query: str, *, limit: int = 20) -> list[Message]:
        q = (query or "").strip()
        if not q:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT m.* FROM lumen_messages m
                JOIN lumen_conversations c ON c.id = m.conversation_id
                WHERE c.user_id=%s AND m.content ILIKE %s
                ORDER BY m.created_at DESC LIMIT %s
                """,
                (int(user_id), f"%{q}%", int(limit)),
            ).fetchall()
        return [self._row_msg(r) for r in rows if r]

    def purge_older_than(self, days: int = 30) -> int:
        cutoff = time.time() - max(1, int(days)) * 86400
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM lumen_conversations WHERE updated_at < %s",
                (cutoff,),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    @staticmethod
    def _row_conv(row: dict) -> Conversation:
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return Conversation(
            id=str(row["id"]),
            user_id=int(row["user_id"]),
            title=str(row.get("title") or ""),
            created_at=float(row.get("created_at") or 0),
            updated_at=float(row.get("updated_at") or 0),
            is_active=bool(row.get("is_active", True)),
            summary=str(row.get("summary") or ""),
            message_count=int(row.get("message_count") or 0),
            metadata=dict(meta) if isinstance(meta, dict) else {},
        )

    @staticmethod
    def _row_msg(row: dict) -> Message:
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return Message(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            user_id=int(row["user_id"]),
            role=str(row.get("role") or "user"),
            content=str(row.get("content") or ""),
            tokens=int(row.get("tokens") or 0),
            created_at=float(row.get("created_at") or 0),
            metadata=dict(meta) if isinstance(meta, dict) else {},
        )


_STORE: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    dsn = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("TBE_DATABASE_URL")
        or ""
    ).strip()
    if dsn:
        try:
            _STORE = PostgresConversationStore(dsn)
            logger.info("conversation store=postgres")
            return _STORE
        except Exception as exc:
            logger.warning("conversation postgres failed: %s — memory fallback", type(exc).__name__)
    _STORE = MemoryConversationStore()
    logger.info("conversation store=memory")
    return _STORE


def reset_conversation_store_for_tests() -> None:
    global _STORE
    _STORE = None
