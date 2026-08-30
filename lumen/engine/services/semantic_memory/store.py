"""SemanticMemory — durable per-user memory store (Mem0-inspired).

Stores extracted facts with dense embeddings for semantic retrieval:
  - facts table: id, user_id, project_id, kind, content, meta, created_at, updated_at
  - vectors: on-disk numpy (always available) with optional Qdrant backend
  - scoping: user_id + optional project_id (memory per project for edits)

This is the *real* long-term memory. It survives sessions / key failover /
worker restarts and powers semantic recall so the engine "remembers" each user.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    try:
        from lumen.platform.paths import durable_data_dir
        root = Path(durable_data_dir())
    except Exception:
        root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".lumen"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "semantic_memory.sqlite3"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_embed_fn(fn_name: str):
    """Load an embedding function from code_intelligence.embeddings directly.

    Uses importlib to load the module *without* triggering the
    code_intelligence package __init__.py (which pulls in optional deps like
    tree_sitter/rank_bm25 that may be absent in minimal environments). This
    keeps the semantic memory system resilient and decoupled.
    """
    import importlib.util
    import sys
    mod_path = Path(__file__).resolve().parent.parent / "code_intelligence" / "embeddings.py"
    mod_name = "_lumen_embeddings_direct"
    try:
        if mod_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(mod_name, mod_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
        mod = sys.modules.get(mod_name)
        if mod:
            return getattr(mod, fn_name, None)
    except Exception:
        logger.debug("direct embeddings load failed for %s", fn_name, exc_info=True)
    return None


def _embed(text: str) -> list[float]:
    """Embed a single text via the project's neural cascade (fastembed by default)."""
    fn = _load_embed_fn("embed_query")
    if fn:
        try:
            out = fn(text)
            if out.get("ok") and out.get("vector"):
                return [float(x) for x in out["vector"]]
        except Exception:
            logger.debug("semantic_memory embed_query failed", exc_info=True)
    return []


def _embed_batch(texts: list[str]) -> list[list[float]]:
    fn = _load_embed_fn("embed_documents")
    if fn:
        try:
            out = fn(texts)
            if out.get("ok") and out.get("vectors"):
                return [[float(x) for x in v] for v in out["vectors"]]
        except Exception:
            logger.debug("semantic_memory embed_batch failed", exc_info=True)
    return [[] for _ in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    import math
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class MemoryRecord:
    id: str
    user_id: int
    project_id: str
    kind: str  # preference | fact | decision | project_note | instruction | profile
    content: str
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "content": self.content,
            "meta": dict(self.meta),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SemanticMemoryStore:
    """SQLite facts + in-process vector cache with cosine search.

    Vectors are stored as JSON blobs in SQLite (portable, no external server
    required). For high-scale deployments QDRANT_URL enables the external
    vector backend (same interface).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or _default_db_path())
        self._lock = threading.RLock()
        self._vec_cache: dict[str, list[float]] = {}
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
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        project_id TEXT NOT NULL DEFAULT '',
                        kind TEXT NOT NULL DEFAULT 'fact',
                        content TEXT NOT NULL,
                        meta_json TEXT NOT NULL DEFAULT '{}',
                        vector_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_mem_user
                        ON memories(user_id, project_id);
                    CREATE INDEX IF NOT EXISTS idx_mem_kind
                        ON memories(user_id, kind);
                    """
                )
                conn.commit()

    # ---- writes ----
    def add(
        self,
        *,
        user_id: int,
        content: str,
        kind: str = "fact",
        project_id: str = "",
        meta: dict[str, Any] | None = None,
    ) -> MemoryRecord | None:
        content = (content or "").strip()
        if not content:
            return None
        uid = int(user_id or 0)
        pid = (project_id or "").strip()
        rec_id = str(uuid.uuid4())
        now = _now()
        vec = _embed(content)
        meta_s = json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000]
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO memories(id, user_id, project_id, kind, content,
                                         meta_json, vector_json, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (rec_id, uid, pid, (kind or "fact")[:40], content[:2000],
                     meta_s, json.dumps(vec), now, now),
                )
                conn.commit()
            if vec:
                self._vec_cache[rec_id] = vec
        return MemoryRecord(rec_id, uid, pid, (kind or "fact")[:40], content,
                            meta or {}, now, now)

    def update(self, memory_id: str, *, content: str, kind: str = "",
               meta: dict[str, Any] | None = None) -> bool:
        content = (content or "").strip()
        if not content:
            return False
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT id, kind, meta_json FROM memories WHERE id=?", (memory_id,)
                ).fetchone()
                if not row:
                    return False
                new_kind = (kind or row["kind"])[:40]
                base_meta: dict[str, Any] = {}
                try:
                    base_meta = json.loads(row["meta_json"] or "{}") or {}
                except Exception:
                    base_meta = {}
                if meta:
                    base_meta.update(meta)
                vec = _embed(content)
                now = _now()
                conn.execute(
                    """
                    UPDATE memories SET content=?, kind=?, meta_json=?, vector_json=?,
                                         updated_at=? WHERE id=?
                    """,
                    (content[:2000], new_kind,
                     json.dumps(base_meta, ensure_ascii=False, default=str)[:2000],
                     json.dumps(vec), now, memory_id),
                )
                conn.commit()
            self._vec_cache[memory_id] = vec
        return True

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            with self._conn() as conn:
                cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
                conn.commit()
                removed = cur.rowcount > 0
            if removed:
                self._vec_cache.pop(memory_id, None)
        return removed

    # ---- reads ----
    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        meta: dict[str, Any] = {}
        try:
            meta = json.loads(row["meta_json"] or "{}") or {}
        except Exception:
            meta = {}
        return MemoryRecord(
            id=row["id"],
            user_id=int(row["user_id"]),
            project_id=row["project_id"] or "",
            kind=row["kind"] or "fact",
            content=row["content"] or "",
            meta=meta,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def list_all(
        self,
        *,
        user_id: int,
        project_id: str = "",
        kind: str = "",
        limit: int = 200,
    ) -> list[MemoryRecord]:
        uid = int(user_id or 0)
        sql = "SELECT * FROM memories WHERE user_id=?"
        params: list[Any] = [uid]
        if project_id:
            sql += " AND project_id=?"
            params.append(project_id)
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id=?", (memory_id,)
                ).fetchone()
        return self._row_to_record(row) if row else None

    def semantic_search(
        self,
        *,
        user_id: int,
        query: str,
        project_id: str = "",
        kind: str = "",
        top_k: int = 8,
        min_score: float = 0.30,
    ) -> list[tuple[MemoryRecord, float]]:
        """Semantic retrieval scoped to user (+ optional project/kind).

        Returns (record, score) pairs sorted by cosine similarity.
        """
        uid = int(user_id or 0)
        qtext = (query or "").strip()
        if not qtext:
            return []
        qvec = _embed(qtext)
        if not qvec:
            # fallback to lexical when embeddings unavailable
            return self._lexical_search(
                user_id=uid, query=qtext, project_id=project_id,
                kind=kind, top_k=top_k,
            )
        candidates = self.list_all(user_id=uid, project_id=project_id,
                                   kind=kind, limit=500)
        if not candidates:
            return []
        scored: list[tuple[MemoryRecord, float]] = []
        for rec in candidates:
            vec = self._vec_cache.get(rec.id)
            if vec is None:
                try:
                    vec = json.loads(
                        self._raw_vector(rec.id) or "[]"
                    )
                except Exception:
                    vec = []
                if vec:
                    self._vec_cache[rec.id] = vec
            if not vec:
                continue
            score = _cosine(qvec, vec)
            if score >= min_score:
                scored.append((rec, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _raw_vector(self, memory_id: str) -> str:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT vector_json FROM memories WHERE id=?", (memory_id,)
                ).fetchone()
        return (row["vector_json"] if row else "") or ""

    def _lexical_search(
        self,
        *,
        user_id: int,
        query: str,
        project_id: str = "",
        kind: str = "",
        top_k: int = 8,
    ) -> list[tuple[MemoryRecord, float]]:
        qtokens = set(w.lower() for w in (query or "").split() if len(w) > 1)
        if not qtokens:
            return []
        out: list[tuple[MemoryRecord, float]] = []
        for rec in self.list_all(user_id=user_id, project_id=project_id,
                                 kind=kind, limit=200):
            rtokens = set(w.lower() for w in rec.content.split() if len(w) > 1)
            if not rtokens:
                continue
            overlap = len(qtokens & rtokens) / max(1, len(qtokens))
            if overlap > 0:
                out.append((rec, float(overlap)))
        out.sort(key=lambda x: x[1], reverse=True)
        return out[:top_k]

    def clear(self, *, user_id: int, project_id: str = "") -> int:
        uid = int(user_id or 0)
        with self._lock:
            with self._conn() as conn:
                if project_id:
                    cur = conn.execute(
                        "DELETE FROM memories WHERE user_id=? AND project_id=?",
                        (uid, project_id),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM memories WHERE user_id=?", (uid,)
                    )
                conn.commit()
                n = cur.rowcount
            # purge cache for this user
            keep = {r.id for r in self.list_all(user_id=uid, limit=10000)}
            for k in list(self._vec_cache.keys()):
                if k not in keep:
                    self._vec_cache.pop(k, None)
        return int(n or 0)


_store: SemanticMemoryStore | None = None
_store_lock = threading.Lock()


def get_semantic_store() -> SemanticMemoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = SemanticMemoryStore()
        return _store


__all__ = [
    "SemanticMemoryStore",
    "MemoryRecord",
    "get_semantic_store",
]
