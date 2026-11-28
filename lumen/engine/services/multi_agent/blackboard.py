"""Blackboard stores — pluggable persistence for AgentState."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .state import AgentState

logger = logging.getLogger(__name__)


class BlackboardStore(ABC):
    @abstractmethod
    def put(self, state: AgentState) -> AgentState:
        ...

    @abstractmethod
    def get(self, state_id: str) -> Optional[AgentState]:
        ...

    @abstractmethod
    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        ...

    @abstractmethod
    def latest_for_principal(self, principal_id: str) -> Optional[AgentState]:
        ...

    @abstractmethod
    def list_ids(self, *, limit: int = 100) -> list[str]:
        ...


class MemoryBlackboard(BlackboardStore):
    """Process-local store with lock — fast, not durable."""

    def __init__(self) -> None:
        self._data: dict[str, AgentState] = {}
        self._lock = threading.RLock()

    def put(self, state: AgentState) -> AgentState:
        with self._lock:
            existing = self._data.get(state.state_id)
            if existing is not None and (
                existing.principal_id != state.principal_id
                or int(existing.user_id or 0) != int(state.user_id or 0)
            ):
                raise PermissionError("agent_state_owner_mismatch")
            state.touch()
            self._data[state.state_id] = state
            return state

    def get(self, state_id: str) -> Optional[AgentState]:
        with self._lock:
            return self._data.get(state_id)

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        # Ambiguous pre-principal records are quarantined. Never expose them
        # to Telegram based only on a colliding numeric user_id.
        return self.latest_for_principal(f"telegram:{int(user_id or 0)}")

    def latest_for_principal(self, principal_id: str) -> Optional[AgentState]:
        principal = str(principal_id or "").strip()
        with self._lock:
            items = [state for state in self._data.values() if state.principal_id == principal]
        return max(items, key=lambda state: state.updated_at) if items else None

    def list_ids(self, *, limit: int = 100) -> list[str]:
        with self._lock:
            ids = sorted(self._data.keys(), key=lambda i: self._data[i].updated_at, reverse=True)
        return ids[: max(1, min(limit, 1000))]


class FileBlackboard(BlackboardStore):
    """Local-development JSON board under OUTPUT_DIR/multi_agent_board/."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen"))
            root = base / "multi_agent_board"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index_path = self.root / "_index.json"

    def _path(self, state_id: str) -> Path:
        safe = "".join(ch for ch in state_id if ch.isalnum() or ch in "-_")[:64]
        return self.root / f"{safe}.json"

    def _write_index(self, state: AgentState) -> None:
        try:
            idx: dict = {}
            if self._index_path.exists():
                idx = json.loads(self._index_path.read_text(encoding="utf-8") or "{}")
            idx[state.state_id] = {
                "user_id": state.user_id,
                "principal_id": state.principal_id,
                "status": state.status,
                "updated_at": state.updated_at,
            }
            # prune index to last 500
            if len(idx) > 500:
                ordered = sorted(idx.items(), key=lambda kv: float(kv[1].get("updated_at") or 0), reverse=True)[:500]
                idx = dict(ordered)
            self._index_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("blackboard index write failed")

    def put(self, state: AgentState) -> AgentState:
        with self._lock:
            existing = self.get(state.state_id)
            if existing is not None and (
                existing.principal_id != state.principal_id
                or int(existing.user_id or 0) != int(state.user_id or 0)
            ):
                raise PermissionError("agent_state_owner_mismatch")
            state.touch()
            path = self._path(state.state_id)
            path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=0), encoding="utf-8")
            self._write_index(state)
            return state

    def get(self, state_id: str) -> Optional[AgentState]:
        with self._lock:
            path = self._path(state_id)
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return AgentState.from_dict(data)
            except Exception:
                logger.exception("blackboard get failed id=%s", state_id)
                return None

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        # Ambiguous pre-principal records are quarantined. Never expose them
        # to Telegram based only on a colliding numeric user_id.
        return self.latest_for_principal(f"telegram:{int(user_id or 0)}")

    def latest_for_principal(self, principal_id: str) -> Optional[AgentState]:
        principal = str(principal_id or "").strip()
        with self._lock:
            if not self._index_path.exists():
                return None
            try:
                index = json.loads(self._index_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                return None
            legacy_user = principal.split(":", 2)[2] if principal.startswith("legacy:user:") else None
            matches = [(sid, meta) for sid, meta in index.items()
                       if (str(meta.get("principal_id") or "") == principal
                           or (legacy_user is not None and not meta.get("principal_id")
                               and str(meta.get("user_id") or "") == legacy_user))]
            if not matches:
                return None
            sid = max(matches, key=lambda item: float(item[1].get("updated_at") or 0))[0]
            return self.get(sid)

    def list_ids(self, *, limit: int = 100) -> list[str]:
        with self._lock:
            if not self._index_path.exists():
                return []
            try:
                idx = json.loads(self._index_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                return []
            ordered = sorted(idx.items(), key=lambda kv: float(kv[1].get("updated_at") or 0), reverse=True)
            return [sid for sid, _ in ordered[: max(1, min(limit, 1000))]]



class PostgresBlackboardStore(BlackboardStore):
    """Shared production AgentState store backed by PostgreSQL JSONB.

    This store is separate from LangGraph's internal checkpoint tables: it is
    the application-level index used by Telegram/API handlers to locate and
    authorize a workflow after it ran on another worker or replica.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS lumen_agent_states (
        state_id TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        principal_id TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL,
        payload JSONB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_lumen_agent_states_user_updated
        ON lumen_agent_states (user_id, updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_lumen_agent_states_status_updated
        ON lumen_agent_states (status, updated_at DESC);
    """

    def __init__(self) -> None:
        from lumen.platform.postgres_pool import get_postgres_pool

        self._pool = get_postgres_pool()
        with self._pool.connection(timeout=10) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lumen_agent_states (
                    state_id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    principal_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL,
                    payload JSONB NOT NULL
                )
                """
            )
            conn.execute(
                """
                ALTER TABLE lumen_agent_states
                ADD COLUMN IF NOT EXISTS principal_id TEXT NOT NULL DEFAULT ''
                """
            )
            # Keep pre-migration records in a quarantined legacy namespace.
            conn.execute(
                """
                UPDATE lumen_agent_states
                SET principal_id = CASE
                        WHEN principal_id = '' THEN 'legacy:user:' || user_id::text
                        ELSE principal_id
                    END,
                    payload = jsonb_set(
                        jsonb_set(
                            payload,
                            '{principal_id}',
                            to_jsonb(CASE
                                WHEN principal_id = '' THEN 'legacy:user:' || user_id::text
                                ELSE principal_id
                            END),
                            true
                        ),
                        '{schema_version}',
                        to_jsonb(3),
                        true
                    )
                WHERE principal_id = ''
                   OR payload->>'schema_version' IS DISTINCT FROM '3'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lumen_agent_states_principal_updated
                ON lumen_agent_states (principal_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lumen_agent_states_user_updated
                ON lumen_agent_states (user_id, updated_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lumen_agent_states_status_updated
                ON lumen_agent_states (status, updated_at DESC)
                """
            )
        logger.info("PostgreSQL AgentState blackboard ready")

    @staticmethod
    def _decode(row: dict | None) -> AgentState | None:
        if not row:
            return None
        payload = row.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("invalid_agent_state_payload")
        state = AgentState.from_dict(payload)
        stored_principal = row.get("principal_id")
        stored_user_id = row.get("user_id")
        if stored_principal is not None and str(stored_principal) != state.principal_id:
            raise ValueError("agent_state_principal_column_mismatch")
        if stored_user_id is not None and int(stored_user_id) != int(state.user_id or 0):
            raise ValueError("agent_state_user_column_mismatch")
        return state

    def put(self, state: AgentState) -> AgentState:
        state.touch()
        payload = json.dumps(
            state.to_dict(), ensure_ascii=False, separators=(",", ":")
        )
        with self._pool.connection(timeout=10) as conn:
            cur = conn.execute(
                """
                INSERT INTO lumen_agent_states
                    (state_id, user_id, principal_id, status, updated_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (state_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                WHERE lumen_agent_states.user_id = EXCLUDED.user_id
                  AND lumen_agent_states.principal_id = EXCLUDED.principal_id
                """,
                (
                    state.state_id,
                    int(state.user_id or 0),
                    str(state.principal_id),
                    str(state.status or ""),
                    float(state.updated_at),
                    payload,
                ),
            )
            if cur.rowcount != 1:
                raise PermissionError("agent_state_owner_mismatch")
        return state

    def get(self, state_id: str) -> Optional[AgentState]:
        with self._pool.connection(timeout=10) as conn:
            row = conn.execute(
                "SELECT payload, principal_id, user_id FROM lumen_agent_states WHERE state_id=%s",
                (str(state_id or ""),),
            ).fetchone()
        return self._decode(row)

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        # Ambiguous pre-principal records are quarantined. Never expose them
        # to Telegram based only on a colliding numeric user_id.
        return self.latest_for_principal(f"telegram:{int(user_id or 0)}")

    def latest_for_principal(self, principal_id: str) -> Optional[AgentState]:
        principal = str(principal_id or "").strip()
        if not principal or len(principal) > 256:
            return None
        with self._pool.connection(timeout=10) as conn:
            row = conn.execute(
                """
                SELECT payload, principal_id, user_id FROM lumen_agent_states
                WHERE principal_id=%s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (principal,),
            ).fetchone()
        return self._decode(row)

    def delete(self, state_id: str) -> bool:
        with self._pool.connection(timeout=10) as conn:
            cur = conn.execute(
                "DELETE FROM lumen_agent_states WHERE state_id=%s",
                (str(state_id or ""),),
            )
        return bool(cur.rowcount)

    def list_ids(self, *, limit: int = 100) -> list[str]:
        bounded = max(1, min(int(limit), 1000))
        with self._pool.connection(timeout=10) as conn:
            rows = conn.execute(
                """
                SELECT state_id FROM lumen_agent_states
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (bounded,),
            ).fetchall()
        return [str(row["state_id"]) for row in rows if row.get("state_id")]



class LayeredBlackboard(BlackboardStore):
    """Local-development memory cache + file mirror."""

    def __init__(self, memory: MemoryBlackboard | None = None, file: FileBlackboard | None = None) -> None:
        self.memory = memory or MemoryBlackboard()
        self.file = file or FileBlackboard()

    def put(self, state: AgentState) -> AgentState:
        try:
            self.file.put(state)
        except PermissionError:
            raise
        except Exception:
            logger.exception("durable blackboard put failed")
        self.memory.put(state)
        return state

    def get(self, state_id: str) -> Optional[AgentState]:
        s = self.memory.get(state_id)
        if s is not None:
            return s
        s = self.file.get(state_id)
        if s is not None:
            self.memory.put(s)
        return s

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        s = self.memory.latest_for_user(user_id)
        if s is not None:
            return s
        s = self.file.latest_for_user(user_id)
        if s is not None:
            self.memory.put(s)
        return s

    def latest_for_principal(self, principal_id: str) -> Optional[AgentState]:
        state = self.memory.latest_for_principal(principal_id)
        if state is not None:
            return state
        state = self.file.latest_for_principal(principal_id)
        if state is not None:
            self.memory.put(state)
        return state

    def list_ids(self, *, limit: int = 100) -> list[str]:
        ids = self.memory.list_ids(limit=limit)
        if ids:
            return ids
        return self.file.list_ids(limit=limit)


_default_board: BlackboardStore | None = None
_board_lock = threading.Lock()


def get_blackboard() -> BlackboardStore:
    """Use shared PostgreSQL in production; local stores are development-only."""
    global _default_board
    with _board_lock:
        if _default_board is None:
            from lumen.platform.runtime_config import is_dev

            if not is_dev():
                # No local-file or in-memory fallback in production: silently
                # degrading here breaks cross-replica HITL and task recovery.
                _default_board = PostgresBlackboardStore()
            else:
                mode = (os.environ.get("MULTI_AGENT_BOARD") or "layered").strip().lower()
                if mode == "memory":
                    _default_board = MemoryBlackboard()
                elif mode == "file":
                    _default_board = FileBlackboard()
                else:
                    _default_board = LayeredBlackboard()
        return _default_board

def set_blackboard(store: BlackboardStore) -> None:
    """Tests / advanced hosts can inject a custom store."""
    global _default_board
    with _board_lock:
        _default_board = store
