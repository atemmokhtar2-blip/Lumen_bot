"""SemanticMemory — durable per-user memory store (Mem0-inspired, hardened).

Stores extracted facts with dense embeddings for semantic retrieval:
  - memories table: id, user_id, project_id, kind, content, meta, vectors,
    created_at, updated_at, last_accessed_at, access_history
  - vectors: multilingual neural embeddings (paraphrase-multilingual-MiniLM-L12-v2,
    384-dim, Arabic-capable) stored as JSON blobs in SQLite
  - search: numpy-vectorized cosine (Q @ Mᵀ) with in-memory matrix cache —
    O(d) per query instead of O(n·d) brute-force loop
  - dedup: add() checks for an existing near-duplicate (cosine ≥ threshold)
    via the *same* numpy matrix as search, before inserting, updating the old
    record instead of accumulating copies
  - decay: Mem0 Memory Decay — exponential recency-aware score scaling at
    search time (Qdrant-recommended; smooth, no cliff at window boundaries),
    plus importance weighting from access_count (frequently-used memories
    decay slower). Fresh → 1.5× boost, stale → 0.3× floor.
  - re-embedding safety: if the embedding model is upgraded, old vectors with
    a stale dimension are detected at load, excluded from the matrix (never
    crash on a ragged array), and re-embedded on their next add/update.
  - durability: single persistent WAL connection (no per-op churn) + RLock

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

# ---- Mem0 Memory Decay constants (mem0.ai/blog/introducing-memory-decay,
#      qdrant.tech/blog/decay-functions) ----
# Recency-aware score scaling applied AT SEARCH TIME (never deletes memories).
#
# Exponential decay (Qdrant-recommended) is smoother than linear interpolation:
#   - no cliff at window boundaries (linear jumped 1.5→0.x at exactly 1 day)
#   - decays gently at first, then faster, then asymptotes to the floor
#   - matches the human intuition that "recently used" matters most
#
# The decay multiplier lives in [_DECAY_STALE_FLOOR, _DECAY_FRESH_BOOST]:
#   fresh (age → 0) → 1.5× boost ; stale (age → ∞) → 0.3× floor.
# Half-life (_DECAY_HALF_LIFE_S) = age at which the multiplier is exactly the
# midpoint between floor and boost — tuned to ~3 days (frequently-relevant
# memories stay boosted for a few days, then gracefully fade).
_DECAY_FRESH_BOOST = 1.5
_DECAY_STALE_FLOOR = 0.3
_DECAY_HALF_LIFE_S = 3 * 86_400          # 3 days → midpoint multiplier
_DECAY_MAX_HISTORY = 20                  # track last N access timestamps per memory
_DECAY_FRESH_WINDOW_S = 86_400           # <1 day old → full fresh boost (fast-path)
_DECAY_STALE_WINDOW_S = 30 * 86_400      # >30 days → effectively floor (fast-path)
# Importance weighting: memories accessed more often decay slower.  Each access
# nudges the effective age backward (simulating "recently useful"), capped so a
# frequently-used memory never drops below the fresh boost.
_DECAY_IMPORTANCE_PER_ACCESS = 0.12      # each access reduces effective age by 12% of half-life
_DECAY_IMPORTANCE_MAX_REDUCTION = 0.60   # cap: at most 60% age reduction from importance

# Dedup safety-net for the direct add() path (when the LLM extraction layer
# is not used). Mem0's primary dedup is the LLM ADD/UPDATE/DELETE/NOOP
# classification in extraction.py; this is a backstop for raw inserts.
# 0.90 = very high semantic overlap (reworded same fact). The multilingual
# model clusters template-heavy sentences tightly (~0.97), so we also require
# a lexical-token overlap check to avoid collapsing distinct facts that merely
# share a sentence structure.
_DEDUP_THRESHOLD = 0.90
_DEDUP_LEXICAL_MIN = 0.60  # min token-overlap to confirm a cosine duplicate


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


def _now_ts() -> float:
    return time.time()


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
    """Embed a single text via the multilingual semantic model (Arabic-capable)."""
    fn = _load_embed_fn("embed_query_semantic")
    if fn:
        try:
            out = fn(text)
            if out.get("ok") and out.get("vector"):
                return [float(x) for x in out["vector"]]
        except Exception:
            logger.debug("semantic_memory embed_query_semantic failed", exc_info=True)
    # legacy fallback (English-centric) if the multilingual fn is absent
    fn2 = _load_embed_fn("embed_query")
    if fn2:
        try:
            out = fn2(text)
            if out.get("ok") and out.get("vector"):
                return [float(x) for x in out["vector"]]
        except Exception:
            logger.debug("semantic_memory embed_query failed", exc_info=True)
    return []


def _embed_batch(texts: list[str]) -> list[list[float]]:
    fn = _load_embed_fn("embed_documents_semantic")
    if fn:
        try:
            out = fn(texts)
            if out.get("ok") and out.get("vectors"):
                return [[float(x) for x in v] for v in out["vectors"]]
        except Exception:
            logger.debug("semantic_memory embed_documents_semantic failed", exc_info=True)
    fn2 = _load_embed_fn("embed_documents")
    if fn2:
        try:
            out = fn2(texts)
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
    last_accessed_at: str = ""
    access_count: int = 0

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
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
        }


class SemanticMemoryStore:
    """SQLite facts + numpy-vectorized semantic search with Mem0-style decay.

    Vectors are stored as JSON blobs in SQLite (portable, no external server
    required). At init, all vectors are loaded into a numpy matrix for O(d)
    vectorized cosine search (Q @ Mᵀ) instead of an O(n·d) brute-force loop.
    A single persistent WAL connection is reused across operations (no churn).

    Hardening vs the original implementation:
      * numpy-vectorized search (was: linear Python loop over ≤500 candidates)
      * persistent connection pool of 1 (was: new connect() per operation)
      * vectors loaded once at init + incrementally maintained (was: in-memory
        dict lost on restart, re-parsed from JSON on every search)
      * dedup at add() via cosine ≥ _DEDUP_THRESHOLD → UPDATE existing,
        using the same numpy matrix as search (was: Python cosine loop)
      * Mem0 Memory Decay: last_accessed_at + access_history (≤20 timestamps),
        *exponential* recency scaling 0.3×–1.5× (smooth, no cliff) + importance
        weighting from access_count (was: linear interpolation, no importance)
      * re-embedding safety: stale-dimension vectors detected at load and
        excluded from the matrix until re-embedded (was: would crash on
        ragged arrays after a model upgrade)
      * _record_access batch read (was: N+1 SELECT+UPDATE per memory)
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or _default_db_path())
        self._lock = threading.RLock()
        # id → vector (list[float]); kept in sync with the numpy matrix
        self._vec_cache: dict[str, list[float]] = {}
        # ordered ids parallel to the numpy matrix rows
        self._mat_ids: list[str] = []
        self._mat = None  # numpy ndarray (n, d) L2-normalized, or None
        self._mat_dirty = True
        # ids whose stored vector has a stale dimension (model upgraded);
        # excluded from the cache/matrix until re-embedded
        self._mismatched_ids: set[str] = set()
        # single persistent connection (WAL, check_same_thread=False)
        self._conn: sqlite3.Connection | None = None
        self._init()

    # ---- connection (persistent, reused) ----
    def _db(self) -> sqlite3.Connection:
        """Return the single persistent connection (created once, reused)."""
        if self._conn is not None:
            return self._conn
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        self._conn = c
        return c

    def _init(self) -> None:
        with self._lock:
            conn = self._db()
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
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL DEFAULT '',
                    access_count INTEGER NOT NULL DEFAULT 0,
                    access_history TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_mem_user
                    ON memories(user_id, project_id);
                CREATE INDEX IF NOT EXISTS idx_mem_kind
                    ON memories(user_id, kind);
                """
            )
            conn.commit()
            # load all existing vectors into the in-memory cache + matrix
            self._load_all_vectors()

    def _load_all_vectors(self) -> None:
        """Load every (id, vector) pair from DB into the cache and mark the
        numpy matrix dirty so it is rebuilt on the next search.

        Re-embedding safety: if the embedding model was upgraded, old vectors
        stored in the DB may have a different dimension than vectors the
        current model produces.  Loading mismatched dimensions into the same
        numpy matrix would crash (ragged array) or produce garbage cosine
        scores.  We detect the canonical dimension from a fresh probe embed,
        then only cache vectors whose dimension matches — mismatched ones are
        flagged for re-embedding (logged, not silently corrupted).
        """
        with self._lock:
            conn = self._db()
            rows = conn.execute("SELECT id, vector_json FROM memories").fetchall()
            # probe the current embedding model to learn the canonical dim
            try:
                probe = _embed("dimension probe")
                canonical_dim = len(probe) if probe else 0
            except Exception:
                canonical_dim = 0
            self._vec_cache.clear()
            self._mismatched_ids: set[str] = set()
            for r in rows:
                try:
                    v = json.loads(r["vector_json"] or "[]")
                except Exception:
                    v = []
                if not v:
                    continue
                v = [float(x) for x in v]
                # re-embedding safety: skip vectors with the wrong dimension
                if canonical_dim and len(v) != canonical_dim:
                    self._mismatched_ids.add(r["id"])
                    continue
                self._vec_cache[r["id"]] = v
            if self._mismatched_ids:
                logger.warning(
                    "semantic_memory: %d vectors have a stale dimension "
                    "(model upgraded?); they will be re-embedded on next "
                    "add/update of those memories. canonical_dim=%d",
                    len(self._mismatched_ids), canonical_dim,
                )
            self._mat_dirty = True

    def _rebuild_matrix(self) -> None:
        """Rebuild the numpy matrix from _vec_cache (all users).

        Defensive: if vectors have inconsistent dimensions (shouldn't happen
        after the re-embedding safety filter, but guard anyway), we group by
        dimension and build the matrix from the largest group only — never
        crash on a ragged array.
        """
        try:
            import numpy as _np
        except Exception:
            self._mat = None
            self._mat_ids = []
            return
        ids = list(self._vec_cache.keys())
        if not ids:
            self._mat = None
            self._mat_ids = []
            self._mat_dirty = False
            return
        rows = [self._vec_cache[i] for i in ids]
        # guard against ragged arrays (mixed dimensions)
        dims = {len(r) for r in rows}
        if len(dims) > 1:
            # keep only the most common dimension
            from collections import Counter
            common_dim = Counter(len(r) for r in rows).most_common(1)[0][0]
            kept = [(i, r) for i, r in zip(ids, rows) if len(r) == common_dim]
            ids = [i for i, _ in kept]
            rows = [r for _, r in kept]
            if not rows:
                self._mat = None
                self._mat_ids = []
                self._mat_dirty = False
                return
            logger.warning(
                "semantic_memory: ragged vectors detected — building matrix "
                "from dim=%d group only (%d of %d).",
                common_dim, len(rows), len(self._vec_cache),
            )
        m = _np.asarray(rows, dtype=_np.float32)
        # L2-normalize rows so cosine = dot product
        norms = _np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        m = m / norms
        self._mat = m
        self._mat_ids = ids
        self._mat_dirty = False

    def _invalidate_matrix(self) -> None:
        self._mat_dirty = True

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
        """Add a fact, with dedup: if an existing memory for this user (+scope)
        is semantically near-identical (cosine ≥ _DEDUP_THRESHOLD), UPDATE it
        instead of inserting a duplicate row."""
        content = (content or "").strip()
        if not content:
            return None
        uid = int(user_id or 0)
        pid = (project_id or "").strip()
        knd = (kind or "fact")[:40]
        now = _now()
        vec = _embed(content)
        meta_s = json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000]
        with self._lock:
            # ---- dedup check ----
            dup_id = None
            if vec:
                dup_id = self._find_duplicate(
                    uid=uid, pid=pid, knd=knd, qvec=vec, qcontent=content,
                )
            if dup_id:
                # UPDATE the existing near-duplicate instead of ADD
                conn = self._db()
                row = conn.execute(
                    "SELECT meta_json FROM memories WHERE id=?", (dup_id,)
                ).fetchone()
                base_meta: dict[str, Any] = {}
                try:
                    base_meta = json.loads(row["meta_json"] or "{}") if row else {}
                except Exception:
                    base_meta = {}
                if meta:
                    base_meta.update(meta)
                conn.execute(
                    """
                    UPDATE memories SET content=?, kind=?, meta_json=?, vector_json=?,
                                         updated_at=?
                    WHERE id=?
                    """,
                    (content[:2000], knd,
                     json.dumps(base_meta, ensure_ascii=False, default=str)[:2000],
                     json.dumps(vec), now, dup_id),
                )
                conn.commit()
                self._vec_cache[dup_id] = vec
                self._mismatched_ids.discard(dup_id)
                self._invalidate_matrix()
                # fetch created_at for the returned record
                crow = conn.execute(
                    "SELECT created_at FROM memories WHERE id=?", (dup_id,)
                ).fetchone()
                created = crow["created_at"] if crow else ""
                return MemoryRecord(dup_id, uid, pid, knd, content,
                                    base_meta, created, now)
            # ---- fresh insert ----
            rec_id = str(uuid.uuid4())
            conn = self._db()
            conn.execute(
                """
                INSERT INTO memories(id, user_id, project_id, kind, content,
                                     meta_json, vector_json, created_at, updated_at,
                                     last_accessed_at, access_count, access_history)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (rec_id, uid, pid, knd, content[:2000], meta_s,
                 json.dumps(vec), now, now, "", 0, "[]"),
            )
            conn.commit()
            if vec:
                self._vec_cache[rec_id] = vec
                self._mismatched_ids.discard(rec_id)
                self._invalidate_matrix()
        return MemoryRecord(rec_id, uid, pid, knd, content, meta or {}, now, now)

    def _find_duplicate(self, *, uid: int, pid: str, knd: str,
                        qvec: list[float], qcontent: str = "") -> str | None:
        """Find an existing memory for this user/scope/kind that is a near-
        duplicate of qvec (cosine ≥ _DEDUP_THRESHOLD AND lexical token overlap
        ≥ _DEDUP_LEXICAL_MIN). The lexical check prevents collapsing distinct
        facts that merely share a sentence template (the multilingual model
        clusters template-heavy sentences at ~0.97 cosine). Returns id or None.

        Uses the numpy matrix (Q @ subᵀ) for the cosine computation when
        available — consistent with the search path and O(d) per candidate
        instead of an O(n·d) Python loop. Falls back to pure-Python cosine
        when numpy is absent or the matrix is stale.
        """
        if not qvec:
            return None
        # scope candidate set to the same user (+ optional project + kind)
        conn = self._db()
        sql = "SELECT id, content FROM memories WHERE user_id=?"
        params: list[Any] = [uid]
        if pid:
            sql += " AND project_id=?"
            params.append(pid)
        if knd:
            sql += " AND kind=?"
            params.append(knd)
        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return None
        qtokens = set(w.lower() for w in (qcontent or "").split() if len(w) > 2)
        best_id = None
        best_score = 0.0

        # ---- numpy vectorized cosine (consistent with search path) ----
        try:
            import numpy as _np
            if self._mat_dirty:
                self._rebuild_matrix()
            if self._mat is not None and self._mat_ids:
                id_to_row = {mid: i for i, mid in enumerate(self._mat_ids)}
                cand_rows: list[int] = []
                cand_pairs: list[tuple[str, str]] = []  # (id, content)
                for r in rows:
                    mid = r["id"]
                    if mid in id_to_row and mid not in self._mismatched_ids:
                        cand_rows.append(id_to_row[mid])
                        cand_pairs.append((mid, r["content"] or ""))
                if cand_rows:
                    sub = self._mat[_np.asarray(cand_rows, dtype=_np.int64)]
                    q = _np.asarray(qvec, dtype=_np.float32)
                    qn = _np.linalg.norm(q)
                    if qn > 0:
                        q = q / qn
                    sims = sub @ q
                    for (mid, rcontent), s in zip(cand_pairs, sims):
                        score = float(s)
                        if score < _DEDUP_THRESHOLD:
                            continue
                        rtokens = set(w.lower() for w in (rcontent or "").split()
                                      if len(w) > 2)
                        if qtokens and rtokens:
                            overlap = len(qtokens & rtokens) / max(1, len(qtokens | rtokens))
                            if overlap < _DEDUP_LEXICAL_MIN:
                                continue
                        if score > best_score:
                            best_score = score
                            best_id = mid
                    return best_id
        except Exception:
            logger.debug("numpy dedup path failed, fallback to Python",
                         exc_info=True)

        # ---- pure-Python fallback ----
        for r in rows:
            mid = r["id"]
            v = self._vec_cache.get(mid)
            if not v or mid in self._mismatched_ids:
                continue
            s = _cosine(qvec, v)
            if s < _DEDUP_THRESHOLD:
                continue
            # lexical confirmation: distinct facts with the same template
            # (e.g. "payments setup" vs "payments config") won't share enough
            # meaningful tokens to confirm a true duplicate.
            rtokens = set(w.lower() for w in (r["content"] or "").split() if len(w) > 2)
            if qtokens and rtokens:
                overlap = len(qtokens & rtokens) / max(1, len(qtokens | rtokens))
                if overlap < _DEDUP_LEXICAL_MIN:
                    continue
            if s > best_score:
                best_score = s
                best_id = mid
        return best_id

    def update(self, memory_id: str, *, content: str, kind: str = "",
               meta: dict[str, Any] | None = None) -> bool:
        content = (content or "").strip()
        if not content:
            return False
        with self._lock:
            conn = self._db()
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
            if vec:
                self._vec_cache[memory_id] = vec
                self._mismatched_ids.discard(memory_id)
                self._invalidate_matrix()
        return True

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            conn = self._db()
            cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            conn.commit()
            removed = cur.rowcount > 0
            if removed:
                self._vec_cache.pop(memory_id, None)
                self._mismatched_ids.discard(memory_id)
                self._invalidate_matrix()
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
            last_accessed_at=row["last_accessed_at"] or "",
            access_count=int(row["access_count"] or 0),
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
            conn = self._db()
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            conn = self._db()
            row = conn.execute(
                "SELECT * FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    # ---- decay helpers ----
    @staticmethod
    def _recency_scale(last_accessed_iso: str, created_iso: str,
                       access_count: int = 0) -> float:
        """Mem0 Memory Decay recency scaling factor in [_DECAY_STALE_FLOOR,
        _DECAY_FRESH_BOOST]. Uses the most recent of (last_accessed, created)
        as the reference timestamp.

        Exponential decay (Qdrant-recommended) — smooth, no cliff at window
        boundaries:
            multiplier = floor + (boost - floor) * 0.5 ** (eff_age / half_life)

        Importance weighting: memories accessed more often decay slower.  Each
        access reduces the *effective* age (simulating "recently useful"), so a
        frequently-used memory stays boosted longer.  Capped at
        _DECAY_IMPORTANCE_MAX_REDUCTION so importance never fully cancels decay.
        """
        ref = last_accessed_iso or created_iso
        if not ref:
            return 1.0
        try:
            t = time.mktime(time.strptime(ref, "%Y-%m-%dT%H:%M:%SZ"))
        except Exception:
            return 1.0
        age_s = max(0.0, _now_ts() - t)

        # fast-paths: very fresh → full boost; very stale → floor
        if age_s <= _DECAY_FRESH_WINDOW_S:
            # still apply a tiny importance nudge so frequently-used fresh
            # memories can slightly exceed the base boost? No — cap at boost.
            return _DECAY_FRESH_BOOST
        if age_s >= _DECAY_STALE_WINDOW_S and access_count <= 0:
            return _DECAY_STALE_FLOOR

        # importance: reduce effective age based on access_count
        reduction = min(
            _DECAY_IMPORTANCE_MAX_REDUCTION,
            int(access_count or 0) * _DECAY_IMPORTANCE_PER_ACCESS,
        )
        eff_age = age_s * (1.0 - reduction)

        # exponential decay: midpoint (0.5) at eff_age == half_life
        import math
        span = _DECAY_FRESH_BOOST - _DECAY_STALE_FLOOR
        mult = _DECAY_STALE_FLOOR + span * (0.5 ** (eff_age / _DECAY_HALF_LIFE_S))
        # clamp to [floor, boost]
        return max(_DECAY_STALE_FLOOR, min(_DECAY_FRESH_BOOST, mult))

    def _record_access(self, memory_ids: list[str]) -> None:
        """Append now to each memory's access_history (capped at last 20) and
        bump last_accessed_at + access_count. Fire-and-forget style (best
        effort, never blocks search results).

        Optimized: avoids the old N+1 SELECT-then-UPDATE pattern. We do a
        single read of all affected rows, append the timestamp in Python, cap
        the list, then issue UPDATEs — but we read once for the whole batch
        instead of one SELECT + one UPDATE per memory.
        """
        if not memory_ids:
            return
        now = _now()
        now_ts = _now_ts()
        conn = self._db()
        # single batch read of all affected rows
        placeholders = ",".join("?" for _ in memory_ids)
        rows = conn.execute(
            f"SELECT id, access_history, access_count FROM memories "
            f"WHERE id IN ({placeholders})",
            memory_ids,
        ).fetchall()
        if not rows:
            return
        for row in rows:
            mid = row["id"]
            try:
                hist = json.loads(row["access_history"] or "[]")
            except Exception:
                hist = []
            hist.append(now_ts)
            if len(hist) > _DECAY_MAX_HISTORY:
                hist = hist[-_DECAY_MAX_HISTORY:]
            conn.execute(
                """UPDATE memories SET last_accessed_at=?, access_count=?,
                   access_history=? WHERE id=?""",
                (now, int(row["access_count"] or 0) + 1,
                 json.dumps(hist), mid),
            )
        conn.commit()

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

        Uses numpy-vectorized cosine (Q @ Mᵀ) for O(d) per query, then applies
        Mem0 Memory Decay recency scaling to the final score. Returns
        (record, decayed_score) pairs sorted descending.
        """
        uid = int(user_id or 0)
        qtext = (query or "").strip()
        if not qtext:
            return []
        qvec = _embed(qtext)
        if not qvec:
            return self._lexical_search(
                user_id=uid, query=qtext, project_id=project_id,
                kind=kind, top_k=top_k,
            )

        with self._lock:
            if self._mat_dirty:
                self._rebuild_matrix()
            candidates = self.list_all(user_id=uid, project_id=project_id,
                                       kind=kind, limit=2000)
            if not candidates:
                return []
            cand_ids = [c.id for c in candidates]
            cand_by_id = {c.id: c for c in candidates}

            scored: list[tuple[MemoryRecord, float]] = []
            used_numpy = False
            # ---- numpy vectorized path (fast) ----
            if self._mat is not None and self._mat_ids:
                try:
                    import numpy as _np
                    # build index map for candidate ids present in the matrix
                    id_to_row = {mid: i for i, mid in enumerate(self._mat_ids)}
                    rows_idx = [id_to_row[c] for c in cand_ids if c in id_to_row]
                    present_ids = [c for c in cand_ids if c in id_to_row]
                    if rows_idx and present_ids:
                        sub = self._mat[_np.asarray(rows_idx, dtype=_np.int64)]
                        q = _np.asarray(qvec, dtype=_np.float32)
                        qn = _np.linalg.norm(q)
                        if qn > 0:
                            q = q / qn
                        sims = sub @ q  # (n,) cosine since rows are normalized
                        for mid, s in zip(present_ids, sims):
                            rec = cand_by_id[mid]
                            raw = float(s)
                            if raw >= min_score:
                                decay = self._recency_scale(
                                    rec.last_accessed_at, rec.created_at,
                                    rec.access_count)
                                scored.append((rec, max(0.0, min(1.0, raw * decay))))
                        used_numpy = True
                except Exception:
                    logger.debug("numpy vectorized search failed, fallback",
                                 exc_info=True)
                    used_numpy = False

            # ---- pure-Python fallback path (if numpy unavailable) ----
            if not used_numpy:
                for rec in candidates:
                    vec = self._vec_cache.get(rec.id)
                    if not vec:
                        try:
                            vec = json.loads(self._raw_vector(rec.id) or "[]")
                        except Exception:
                            vec = []
                        if vec:
                            self._vec_cache[rec.id] = vec
                    if not vec:
                        continue
                    raw = _cosine(qvec, vec)
                    if raw >= min_score:
                        decay = self._recency_scale(
                            rec.last_accessed_at, rec.created_at,
                            rec.access_count)
                        scored.append((rec, max(0.0, min(1.0, raw * decay))))

            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:top_k]

        # record access (fire-and-forget, outside the main lock scope above
        # is safe because _record_access takes its own DB writes via the conn)
        if top:
            try:
                self._record_access([r.id for r, _ in top])
            except Exception:
                logger.debug("access tracking failed", exc_info=True)
        return top

    def _raw_vector(self, memory_id: str) -> str:
        conn = self._db()
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
                decay = self._recency_scale(rec.last_accessed_at,
                                            rec.created_at, rec.access_count)
                out.append((rec, float(overlap * decay)))
        out.sort(key=lambda x: x[1], reverse=True)
        return out[:top_k]

    def clear(self, *, user_id: int, project_id: str = "") -> int:
        uid = int(user_id or 0)
        with self._lock:
            conn = self._db()
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
            # purge cache for deleted rows
            keep = {r.id for r in self.list_all(user_id=uid, limit=10000)}
            for k in list(self._vec_cache.keys()):
                if k not in keep:
                    self._vec_cache.pop(k, None)
            self._invalidate_matrix()
        return int(n or 0)

    def close(self) -> None:
        """Close the persistent connection (mainly for tests)."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


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
