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
    def list_ids(self, *, limit: int = 100) -> list[str]:
        ...


class MemoryBlackboard(BlackboardStore):
    """Process-local store with lock — fast, not durable."""

    def __init__(self) -> None:
        self._data: dict[str, AgentState] = {}
        self._lock = threading.RLock()

    def put(self, state: AgentState) -> AgentState:
        with self._lock:
            state.touch()
            self._data[state.state_id] = state
            return state

    def get(self, state_id: str) -> Optional[AgentState]:
        with self._lock:
            return self._data.get(state_id)

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        with self._lock:
            items = [s for s in self._data.values() if int(s.user_id or 0) == int(user_id or 0)]
        if not items:
            return None
        return max(items, key=lambda s: s.updated_at)

    def list_ids(self, *, limit: int = 100) -> list[str]:
        with self._lock:
            ids = sorted(self._data.keys(), key=lambda i: self._data[i].updated_at, reverse=True)
        return ids[: max(1, min(limit, 1000))]


class FileBlackboard(BlackboardStore):
    """Durable JSON board under OUTPUT_DIR/multi_agent_board/ — scalable across restarts."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".capability_maestro"))
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
        with self._lock:
            if not self._index_path.exists():
                return None
            try:
                idx = json.loads(self._index_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                return None
            candidates = [
                (sid, meta) for sid, meta in idx.items()
                if int(meta.get("user_id") or 0) == int(user_id or 0)
            ]
            if not candidates:
                return None
            sid = max(candidates, key=lambda x: float(x[1].get("updated_at") or 0))[0]
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


class LayeredBlackboard(BlackboardStore):
    """Memory first + durable file mirror — fast path with durability."""

    def __init__(self, memory: MemoryBlackboard | None = None, file: FileBlackboard | None = None) -> None:
        self.memory = memory or MemoryBlackboard()
        self.file = file or FileBlackboard()

    def put(self, state: AgentState) -> AgentState:
        self.memory.put(state)
        try:
            self.file.put(state)
        except Exception:
            logger.exception("durable blackboard put failed")
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

    def list_ids(self, *, limit: int = 100) -> list[str]:
        ids = self.memory.list_ids(limit=limit)
        if ids:
            return ids
        return self.file.list_ids(limit=limit)


_default_board: BlackboardStore | None = None
_board_lock = threading.Lock()


def get_blackboard() -> BlackboardStore:
    global _default_board
    with _board_lock:
        if _default_board is None:
            mode = (os.environ.get("MULTI_AGENT_BOARD") or "layered").strip().lower()
            if mode == "memory":
                _default_board = MemoryBlackboard()
            elif mode == "file":
                _default_board = FileBlackboard()
            else:
                try:
                    from .redis_board import RedisLayeredBlackboard, redis_board_enabled
                    if redis_board_enabled():
                        _default_board = RedisLayeredBlackboard()
                    else:
                        _default_board = LayeredBlackboard()
                except Exception:
                    _default_board = LayeredBlackboard()
        return _default_board


def set_blackboard(store: BlackboardStore) -> None:
    """Tests / advanced hosts can inject a custom store."""
    global _default_board
    with _board_lock:
        _default_board = store
