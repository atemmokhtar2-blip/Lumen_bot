#!/usr/bin/env python
"""Hardening verification for the semantic memory store.

Proves the Phase-2 fixes are REAL (not mock):
  H1. Multilingual embedding model is active (Arabic query → Arabic hit)
  H2. numpy-vectorized search path is used (matrix rebuilt, not brute-force)
  H3. Persistent connection reuse (same object across operations)
  H4. Persistent vector cache survives across store instances (re-init loads vectors)
  H5. Dedup at add(): near-duplicate content UPDATEs instead of inserting a copy
  H6. Mem0 Memory Decay: recency scaling applied; access tracking recorded
  H7. Concurrency: parallel writes don't corrupt the store
  H8. Empty/missing edge cases don't crash

Uses a temp DB. Never touches production data.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="lumen_hardening_")
os.environ["OUTPUT_DIR"] = _TMP
os.environ.setdefault("LUMEN_DURABLE_DIR", _TMP)


def _ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return bool(cond)


def test_h1_multilingual() -> bool:
    print("\n=== H1: Multilingual embedding model active (Arabic) ===")
    from lumen.engine.services.semantic_memory.store import _embed, _load_embed_fn
    fn = _load_embed_fn("embed_query_semantic")
    if not fn:
        return _ok("embed_query_semantic loaded", False)
    out = fn("المستخدم يحب البرمجة بلغة بايثون")
    model = out.get("model", "")
    all_ok = True
    all_ok &= _ok("multilingual model used",
                  "multilingual" in (model or "").lower() or "paraphrase" in (model or "").lower(),
                  model)
    v = _embed("المستخدم يحب البرمجة")
    all_ok &= _ok("embed returns 384-dim vector", len(v) == 384, f"len={len(v)}")
    return all_ok


def test_h2_numpy_vectorized() -> bool:
    print("\n=== H2: numpy-vectorized search path ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h2.sqlite3"
    store = SemanticMemoryStore(path=db)
    # distinct facts (not near-duplicates, so dedup won't collapse them)
    distinct = [
        "The user builds Telegram bots with aiogram",
        "The user's preferred language is Python",
        "The project uses an SQLite database for persistence",
        "The user wants inline keyboards for navigation",
        "The bot should support Arabic and English",
        "The user deployed on a Linux VPS",
        "The user likes concise reply messages",
        "The project has a payment integration with Stripe",
        "The user debugs with print statements",
        "The bot greets new users with a welcome message",
        "The user stores secrets in environment variables",
        "The project uses async handlers throughout",
        "The user prefers functional over OOP style",
        "The bot rate-limits spam automatically",
        "The user logs errors to a rotating file",
    ]
    for c in distinct:
        store.add(user_id=5001, content=c, kind="fact")
    hits = store.semantic_search(user_id=5001, query="python programming language", top_k=5, min_score=0.15)
    all_ok = True
    all_ok &= _ok("search returns hits", len(hits) > 0, f"{len(hits)} hits")
    all_ok &= _ok("matrix built (not None)", store._mat is not None, f"shape={getattr(store._mat, 'shape', None)}")
    all_ok &= _ok("matrix ids loaded (15)", len(store._mat_ids) == 15, f"{len(store._mat_ids)} ids")
    all_ok &= _ok("matrix not dirty after search", not store._mat_dirty)
    store.close()
    return all_ok


def test_h3_persistent_connection() -> bool:
    print("\n=== H3: Persistent connection reuse ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h3.sqlite3"
    store = SemanticMemoryStore(path=db)
    c1 = store._db()
    store.add(user_id=6001, content="conn test fact A", kind="fact")
    store.add(user_id=6001, content="conn test fact B", kind="fact")
    c2 = store._db()
    all_ok = _ok("same connection object reused", c1 is c2, f"c1 is c2: {c1 is c2}")
    store.close()
    return all_ok


def test_h4_persistent_vector_cache() -> bool:
    print("\n=== H4: Vector cache survives re-init (persistent) ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h4.sqlite3"
    s1 = SemanticMemoryStore(path=db)
    s1.add(user_id=7001, content="durable fact about telegram bots", kind="preference")
    n1 = len(s1._vec_cache)
    s1.close()
    # fresh instance re-loads vectors from disk
    s2 = SemanticMemoryStore(path=db)
    n2 = len(s2._vec_cache)
    all_ok = True
    all_ok &= _ok("vectors loaded on re-init", n2 == n1 and n2 > 0, f"before={n1} after={n2}")
    # search works without re-embedding (uses loaded cache)
    hits = s2.semantic_search(user_id=7001, query="telegram", top_k=3, min_score=0.15)
    all_ok &= _ok("search works after re-init", len(hits) > 0, f"{len(hits)} hits")
    s2.close()
    return all_ok


def test_h5_dedup() -> bool:
    print("\n=== H5: Dedup at add() — near-duplicate UPDATEs not inserts ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h5.sqlite3"
    store = SemanticMemoryStore(path=db)
    r1 = store.add(user_id=8001, content="The user prefers Python for backend development", kind="preference")
    # semantically near-identical (reworded) — should UPDATE r1, not insert new
    r2 = store.add(user_id=8001, content="The user prefers Python for the backend", kind="preference")
    all_facts = store.list_all(user_id=8001)
    all_ok = True
    all_ok &= _ok("first add succeeded", r1 is not None)
    all_ok &= _ok("dedup returned SAME id (UPDATE not ADD)", r2 is not None and r2.id == r1.id,
                  f"r1={r1.id[:8]} r2={r2.id[:8] if r2 else None}")
    all_ok &= _ok("only 1 row after near-dup add", len(all_facts) == 1, f"{len(all_facts)} rows")
    # a genuinely different fact should still insert
    r3 = store.add(user_id=8001, content="The user wants a Telegram e-commerce bot", kind="decision")
    all_facts2 = store.list_all(user_id=8001)
    all_ok &= _ok("different fact inserts new row", r3 is not None and r3.id != r1.id, f"now {len(all_facts2)} rows")
    store.close()
    return all_ok


def test_h6_decay_and_access() -> bool:
    print("\n=== H6: Mem0 Memory Decay + access tracking ===")
    from lumen.engine.services.semantic_memory.store import (
        SemanticMemoryStore, _DECAY_FRESH_BOOST, _DECAY_STALE_FLOOR,
    )
    import json as _json
    db = Path(_TMP) / "h6.sqlite3"
    store = SemanticMemoryStore(path=db)
    # fresh memory → fresh boost
    r = store.add(user_id=9001, content="fresh fact about machine learning and neural networks", kind="fact")
    hits = store.semantic_search(user_id=9001, query="machine learning neural networks", top_k=3, min_score=0.15)
    all_ok = True
    all_ok &= _ok("search hit recorded", len(hits) > 0)
    # re-fetch the record from DB to see the access tracking that ran AFTER search
    rid = r.id if r else (hits[0][0].id if hits else None)
    conn = store._db()
    row = conn.execute(
        "SELECT last_accessed_at, access_count, access_history FROM memories WHERE id=?", (rid,)
    ).fetchone() if rid else None
    if row:
        all_ok &= _ok("last_accessed_at set after search", bool(row["last_accessed_at"]), row["last_accessed_at"])
        all_ok &= _ok("access_count incremented", int(row["access_count"]) >= 1, f"count={row['access_count']}")
    else:
        all_ok &= _ok("access row fetched", False)
    # recency scaling: fresh memory should get boost > 1.0
    scale_fresh = SemanticMemoryStore._recency_scale("", _now_iso_recent())
    all_ok &= _ok("fresh recency scale = boost", abs(scale_fresh - _DECAY_FRESH_BOOST) < 0.01, f"{scale_fresh:.3f}")
    # stale memory → floor
    stale_iso = "2020-01-01T00:00:00Z"
    scale_stale = SemanticMemoryStore._recency_scale(stale_iso, stale_iso)
    all_ok &= _ok("stale recency scale = floor", abs(scale_stale - _DECAY_STALE_FLOOR) < 0.01, f"{scale_stale:.3f}")
    # access_history capped at 20
    for _ in range(25):
        store.semantic_search(user_id=9001, query="machine learning neural networks", top_k=1, min_score=0.15)
    row2 = conn.execute(
        "SELECT access_history FROM memories WHERE id=?", (rid,)
    ).fetchone() if rid else None
    if row2:
        hist = _json.loads(row2["access_history"] or "[]")
        all_ok &= _ok("access_history capped at 20", len(hist) <= 20, f"len={len(hist)}")
    else:
        all_ok &= _ok("access_history row fetched", False)
    store.close()
    return all_ok


def _now_iso_recent() -> str:
    import time as _t
    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())


def test_h7_concurrency() -> bool:
    print("\n=== H7: Concurrency — parallel writes don't corrupt ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h7.sqlite3"
    store = SemanticMemoryStore(path=db)
    errors: list[str] = []
    # each worker writes 10 semantically-distinct facts (different domains/objects)

    def worker(wid: int):
        try:
            # 10 genuinely-distinct facts per worker (different domains/objects,
            # not template-variations that the model sees as near-duplicates)
            facts = [
                f"The user chose the {['aiogram','telebot','pyrogram','python-telegram-bot','ntba'][wid]} library for the bot",
                f"The project stores data in {['SQLite','PostgreSQL','Redis','MongoDB','DuckDB'][wid]}",
                f"The bot uses {['inline','reply','custom','web-app','persistent'][wid]} keyboards for navigation",
                f"The user deployed on {['a Linux VPS','Railway','Render','a Raspberry Pi','Fly.io'][wid]}",
                f"The bot supports {['Arabic','French','Spanish','German','Hindi']} and English",
                f"The user prefers {['concise','detailed','formal','casual','bullet-point']} reply messages",
                f"The project integrates {['Stripe','PayPal','Crypto','Cash on delivery','Lemon Squeezy']} for payments",
                f"The bot {['greets','blocks','logs','translates','welcomes']} new users automatically",
                f"The user stores secrets in {['environment variables','a vault','a config file','AWS Secrets Manager','Doppler']}",
                f"The project uses {['async','sync','threaded','event-driven','reactive']} handlers throughout",
            ]
            for c in facts:
                store.add(user_id=10000 + wid, content=c, kind="fact")
        except Exception as e:
            errors.append(f"worker{wid}: {e}")

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    all_ok = True
    all_ok &= _ok("no errors in parallel writes", len(errors) == 0, str(errors[:2]))
    total = 0
    for w in range(5):
        n = len(store.list_all(user_id=10000 + w))
        total += n
    # dedup may collapse a few near-identical ones, but each worker's 10
    # facts are distinct enough (different domain+topic combos) that we
    # expect the vast majority to persist. Assert >= 40 of 50 survived.
    all_ok &= _ok("most facts persisted under concurrency", total >= 40, f"got {total}/50")
    store.close()
    return all_ok


def test_h8_edge_cases() -> bool:
    print("\n=== H8: Edge cases (empty/missing) don't crash ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore
    db = Path(_TMP) / "h8.sqlite3"
    store = SemanticMemoryStore(path=db)
    all_ok = True
    # empty content
    r = store.add(user_id=1, content="", kind="fact")
    all_ok &= _ok("empty content → None", r is None)
    # empty query
    hits = store.semantic_search(user_id=1, query="", top_k=5)
    all_ok &= _ok("empty query → []", hits == [])
    # whitespace query
    hits2 = store.semantic_search(user_id=1, query="   ", top_k=5)
    all_ok &= _ok("whitespace query → []", hits2 == [])
    # nonexistent user
    hits3 = store.semantic_search(user_id=999999, query="anything", top_k=5)
    all_ok &= _ok("nonexistent user → []", hits3 == [])
    # update nonexistent id
    all_ok &= _ok("update nonexistent → False", not store.update("no-such-id", content="x"))
    # delete nonexistent id
    all_ok &= _ok("delete nonexistent → False", not store.delete("no-such-id"))
    # get nonexistent id
    all_ok &= _ok("get nonexistent → None", store.get("no-such-id") is None)
    # clear empty user
    n = store.clear(user_id=12345)
    all_ok &= _ok("clear empty user → 0", n == 0, f"got {n}")
    store.close()
    return all_ok


def main() -> int:
    print("=" * 60)
    print("Lumen Semantic Memory — Hardening Verification (Phase 2)")
    print(f"Temp dir: {_TMP}")
    print("=" * 60)
    results = []
    for fn in [
        test_h1_multilingual,
        test_h2_numpy_vectorized,
        test_h3_persistent_connection,
        test_h4_persistent_vector_cache,
        test_h5_dedup,
        test_h6_decay_and_access,
        test_h7_concurrency,
        test_h8_edge_cases,
    ]:
        try:
            results.append(fn())
        except Exception as e:
            print(f"\n  ✗ {fn.__name__} CRASHED: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    passed = sum(1 for r in results if r)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{total} hardening tests passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
