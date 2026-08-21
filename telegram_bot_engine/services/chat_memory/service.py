"""Durable per-user chat memory for Maestro.

Why: chat providers/keys rotate (Groq↔Gemini, key_0..150). Stateless model
calls would forget the thread. This store keeps:
  - recent turns (user/assistant) with provider tag
  - rolling Arabic/English summary of older turns
  - sticky facts (last bot request, pending action, plan snapshot)

Loaded into every chat_request SERVER_CONTEXT so any key continues the story.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TURNS = int(os.getenv("CHAT_MEMORY_MAX_TURNS") or "40")
_RECENT_FOR_LLM = int(os.getenv("CHAT_MEMORY_RECENT") or "16")
_SUMMARY_EVERY = int(os.getenv("CHAT_MEMORY_SUMMARY_EVERY") or "8")


def _default_db_path() -> Path:
    try:
        from b2b_platform.paths import default_output_dir

        root = Path(default_output_dir())
    except Exception:
        root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".capability_maestro"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "chat_memory.sqlite3"


class ChatMemory:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or _default_db_path())
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        return c

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS chat_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        provider TEXT DEFAULT '',
                        meta_json TEXT DEFAULT '{}',
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_chat_turns_user
                        ON chat_turns(user_id, id);
                    CREATE TABLE IF NOT EXISTS chat_state (
                        user_id INTEGER PRIMARY KEY,
                        summary TEXT NOT NULL DEFAULT '',
                        facts_json TEXT NOT NULL DEFAULT '{}',
                        turn_count INTEGER NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL
                    );
                    """
                )
                conn.commit()

    def append(
        self,
        user_id: int,
        role: str,
        content: str,
        *,
        provider: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        uid = int(user_id)
        text = (content or "").strip()
        if not text:
            return
        role_n = (role or "user")[:20]
        meta_s = json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000]
        now = time.time()
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_turns(user_id, role, content, provider, meta_json, created_at)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (uid, role_n, text[:4000], (provider or "")[:40], meta_s, now),
                )
                row = conn.execute(
                    "SELECT turn_count, summary, facts_json FROM chat_state WHERE user_id=?",
                    (uid,),
                ).fetchone()
                if row:
                    count = int(row["turn_count"] or 0) + 1
                    summary = row["summary"] or ""
                    facts = row["facts_json"] or "{}"
                else:
                    count = 1
                    summary = ""
                    facts = "{}"
                # prune old turns beyond max
                conn.execute(
                    """
                    DELETE FROM chat_turns WHERE user_id=? AND id NOT IN (
                        SELECT id FROM chat_turns WHERE user_id=?
                        ORDER BY id DESC LIMIT ?
                    )
                    """,
                    (uid, uid, max(10, _MAX_TURNS)),
                )
                conn.execute(
                    """
                    INSERT INTO chat_state(user_id, summary, facts_json, turn_count, updated_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        turn_count=excluded.turn_count,
                        updated_at=excluded.updated_at
                    """,
                    (uid, summary, facts, count, now),
                )
                conn.commit()
        # rolling extractive summary without calling an LLM (deterministic, cheap)
        if count % max(2, _SUMMARY_EVERY) == 0:
            try:
                self._refresh_summary(uid)
            except Exception:
                logger.exception("chat_memory summary refresh failed user=%s", uid)

    def set_facts(self, user_id: int, **facts: Any) -> None:
        uid = int(user_id)
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT facts_json, summary, turn_count FROM chat_state WHERE user_id=?",
                    (uid,),
                ).fetchone()
                base: dict[str, Any] = {}
                if row and row["facts_json"]:
                    try:
                        base = json.loads(row["facts_json"]) or {}
                    except Exception:
                        base = {}
                for k, v in facts.items():
                    if v is None:
                        base.pop(k, None)
                    else:
                        base[k] = v
                summary = (row["summary"] if row else "") or ""
                count = int(row["turn_count"] if row else 0)
                conn.execute(
                    """
                    INSERT INTO chat_state(user_id, summary, facts_json, turn_count, updated_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        facts_json=excluded.facts_json,
                        updated_at=excluded.updated_at
                    """,
                    (uid, summary, json.dumps(base, ensure_ascii=False, default=str), count, time.time()),
                )
                conn.commit()

    def _refresh_summary(self, user_id: int) -> None:
        """Compress older turns into a short bullet summary (no external LLM)."""
        turns = self.recent_turns(user_id, limit=_MAX_TURNS)
        if len(turns) < 4:
            return
        older = turns[: -max(4, _RECENT_FOR_LLM // 2)]
        bullets: list[str] = []
        for t in older[-20:]:
            role = t.get("role") or "user"
            text = (t.get("content") or "").replace("\n", " ").strip()
            if not text:
                continue
            prefix = "المستخدم" if role == "user" else "Maestro"
            bullets.append(f"- {prefix}: {text[:160]}")
        if not bullets:
            return
        summary = "ملخص المحادثة السابقة:\n" + "\n".join(bullets[-12:])
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT facts_json, turn_count FROM chat_state WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                facts = (row["facts_json"] if row else None) or "{}"
                count = int(row["turn_count"] if row else 0)
                conn.execute(
                    """
                    INSERT INTO chat_state(user_id, summary, facts_json, turn_count, updated_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        summary=excluded.summary,
                        updated_at=excluded.updated_at
                    """,
                    (int(user_id), summary[:4000], facts, count, time.time()),
                )
                conn.commit()

    def recent_turns(self, user_id: int, *, limit: int | None = None) -> list[dict[str, Any]]:
        lim = int(limit or _RECENT_FOR_LLM)
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content, provider, meta_json, created_at
                    FROM chat_turns WHERE user_id=?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (int(user_id), lim),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in reversed(list(rows)):
            meta = {}
            try:
                meta = json.loads(r["meta_json"] or "{}")
            except Exception:
                meta = {}
            out.append(
                {
                    "role": r["role"],
                    "content": r["content"],
                    "provider": r["provider"] or "",
                    "meta": meta,
                    "ts": r["created_at"],
                }
            )
        return out

    def get_state(self, user_id: int) -> dict[str, Any]:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT summary, facts_json, turn_count, updated_at FROM chat_state WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
        if not row:
            return {"summary": "", "facts": {}, "turn_count": 0}
        facts: dict[str, Any] = {}
        try:
            facts = json.loads(row["facts_json"] or "{}") or {}
        except Exception:
            facts = {}
        return {
            "summary": row["summary"] or "",
            "facts": facts,
            "turn_count": int(row["turn_count"] or 0),
            "updated_at": row["updated_at"],
        }

    def context_for_llm(self, user_id: int) -> dict[str, Any]:
        """Payload to merge into chat SERVER_CONTEXT / conversation_history."""
        state = self.get_state(user_id)
        turns = self.recent_turns(user_id, limit=_RECENT_FOR_LLM)
        history = [
            {"role": t["role"], "content": t["content"]}
            for t in turns
            if t.get("content")
        ]
        return {
            "conversation_history": history,
            "conversation_summary": state.get("summary") or "",
            "memory_facts": state.get("facts") or {},
            "memory_turn_count": state.get("turn_count") or 0,
        }

    def clear(self, user_id: int) -> None:
        uid = int(user_id)
        with self._lock:
            with self._conn() as conn:
                conn.execute("DELETE FROM chat_turns WHERE user_id=?", (uid,))
                conn.execute("DELETE FROM chat_state WHERE user_id=?", (uid,))
                conn.commit()


_store: ChatMemory | None = None
_store_lock = threading.Lock()


def get_chat_memory() -> ChatMemory:
    global _store
    with _store_lock:
        if _store is None:
            _store = ChatMemory()
        return _store


__all__ = ["ChatMemory", "get_chat_memory"]
