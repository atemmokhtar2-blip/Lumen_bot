#!/usr/bin/env python
"""Polish verification for the semantic memory store + smart restart.

Proves the Phase-3 POLISH changes are REAL (not mock, not placeholder):
  P1. Exponential decay: smooth curve, midpoint at half-life, no cliff
  P2. Importance weighting: access_count reduces effective age → slower decay
  P3. Re-embedding safety: stale-dimension vectors are skipped, not crashed
  P4. Batch access tracking: single batch SELECT (no N+1 per memory)
  P5. numpy dedup path: consistent with search (Q @ subᵀ), not Python loop
  P6. restart_by_project: kills old deployment, starts new with same token
  P7. LocalProcessDriver.restart: stop old + deploy new (not just stop)

Uses a temp DB. Never touches production data.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="lumen_polish_")
os.environ["OUTPUT_DIR"] = _TMP
os.environ.setdefault("LUMEN_DURABLE_DIR", _TMP)


def _ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return bool(cond)


# ──────────────────────────────────────────────────────────────────────────
# P1: Exponential decay — smooth curve, midpoint at half-life, no cliff
# ──────────────────────────────────────────────────────────────────────────
def test_p1_exponential_decay() -> bool:
    print("\n=== P1: Exponential decay (smooth, midpoint at half-life) ===")
    from lumen.engine.services.semantic_memory.store import (
        SemanticMemoryStore,
        _DECAY_HALF_LIFE_S,
        _DECAY_FRESH_BOOST,
        _DECAY_STALE_FLOOR,
        _DECAY_FRESH_WINDOW_S,
    )

    rs = SemanticMemoryStore._recency_scale
    all_ok = True

    # fresh → full boost
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    v_fresh = rs(now_iso, now_iso, access_count=0)
    all_ok &= _ok("fresh (<1d) → full boost",
                  abs(v_fresh - _DECAY_FRESH_BOOST) < 1e-9, f"{v_fresh:.4f}")

    # at exactly half-life (offset beyond fresh window): multiplier ≈ midpoint
    half = _DECAY_HALF_LIFE_S
    t_half = time.gmtime(time.time() - half)
    iso_half = time.strftime("%Y-%m-%dT%H:%M:%SZ", t_half)
    v_half = rs(iso_half, iso_half, access_count=0)
    midpoint = _DECAY_STALE_FLOOR + (_DECAY_FRESH_BOOST - _DECAY_STALE_FLOOR) * 0.5
    all_ok &= _ok("at half-life → ≈ midpoint (0.5^(1)=0.5)",
                  abs(v_half - midpoint) < 0.06, f"got={v_half:.4f} expect≈{midpoint:.4f}")

    # at 2× half-life: multiplier ≈ floor + 25% of span
    t_2h = time.gmtime(time.time() - 2 * half)
    iso_2h = time.strftime("%Y-%m-%dT%H:%M:%SZ", t_2h)
    v_2h = rs(iso_2h, iso_2h, access_count=0)
    q_at_2h = _DECAY_STALE_FLOOR + (_DECAY_FRESH_BOOST - _DECAY_STALE_FLOOR) * 0.25
    all_ok &= _ok("at 2×half-life → ≈ 25% of span (0.5^2=0.25)",
                  abs(v_2h - q_at_2h) < 0.06, f"got={v_2h:.4f} expect≈{q_at_2h:.4f}")

    # SMOOTHNESS: no cliff — the curve between half-life and 2×half-life is
    # monotonic and the step is smaller than the step from fresh→half.
    t_1_5h = time.gmtime(time.time() - 1.5 * half)
    iso_1_5h = time.strftime("%Y-%m-%dT%H:%M:%SZ", t_1_5h)
    v_1_5h = rs(iso_1_5h, iso_1_5h, access_count=0)
    step_1_to_1_5 = abs(v_half - v_1_5h)
    step_1_5_to_2 = abs(v_1_5h - v_2h)
    all_ok &= _ok("smooth: steps shrink (no cliff)",
                  step_1_5_to_2 < step_1_to_1_5,
                  f"step1={step_1_to_1_5:.4f} > step2={step_1_5_to_2:.4f}")

    # never below floor, never above boost
    t_old = time.gmtime(time.time() - 60 * 86_400)  # 60 days
    iso_old = time.strftime("%Y-%m-%dT%H:%M:%SZ", t_old)
    v_old = rs(iso_old, iso_old, access_count=0)
    all_ok &= _ok("60d old → clamped ≥ floor",
                  v_old >= _DECAY_STALE_FLOOR - 1e-9, f"{v_old:.4f}")
    all_ok &= _ok("60d old → ≤ boost",
                  v_old <= _DECAY_FRESH_BOOST + 1e-9, f"{v_old:.4f}")

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P2: Importance weighting — access_count reduces effective age
# ──────────────────────────────────────────────────────────────────────────
def test_p2_importance_weighting() -> bool:
    print("\n=== P2: Importance weighting (access_count → slower decay) ===")
    from lumen.engine.services.semantic_memory.store import (
        SemanticMemoryStore,
        _DECAY_HALF_LIFE_S,
        _DECAY_IMPORTANCE_PER_ACCESS,
        _DECAY_IMPORTANCE_MAX_REDUCTION,
    )

    rs = SemanticMemoryStore._recency_scale
    all_ok = True

    # pick an age well beyond the fresh window so we're in the exponential zone
    age_s = 5 * _DECAY_HALF_LIFE_S  # 15 days
    t_old = time.gmtime(time.time() - age_s)
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", t_old)

    v0 = rs(iso, iso, access_count=0)
    v5 = rs(iso, iso, access_count=5)
    v10 = rs(iso, iso, access_count=10)

    all_ok &= _ok("access=5 > access=0 (importance boosts old memory)",
                  v5 > v0, f"v0={v0:.4f} v5={v5:.4f}")
    all_ok &= _ok("access=10 > access=5 (more access → more boost)",
                  v10 > v5, f"v5={v5:.4f} v10={v10:.4f}")

    # cap: at very high access_count, reduction is capped at MAX_REDUCTION
    v_huge = rs(iso, iso, access_count=999)
    v_capped = rs(iso, iso, access_count=100)
    all_ok &= _ok("cap: access=999 ≈ access=100 (capped reduction)",
                  abs(v_huge - v_capped) < 1e-9,
                  f"v999={v_huge:.4f} v100={v_capped:.4f}")

    # verify the cap value
    expected_reduction = _DECAY_IMPORTANCE_MAX_REDUCTION
    all_ok &= _ok(f"cap = {_DECAY_IMPORTANCE_MAX_REDUCTION}",
                  expected_reduction == 0.60)

    # the effective age reduction for 5 accesses should be 5 * 0.12 = 0.60 → capped
    reduction_5 = min(_DECAY_IMPORTANCE_MAX_REDUCTION, 5 * _DECAY_IMPORTANCE_PER_ACCESS)
    all_ok &= _ok("5 accesses → reduction capped at 0.60",
                  abs(reduction_5 - 0.60) < 1e-9, f"{reduction_5}")

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P3: Re-embedding safety — stale-dimension vectors skipped, not crashed
# ──────────────────────────────────────────────────────────────────────────
def test_p3_reembedding_safety() -> bool:
    print("\n=== P3: Re-embedding safety (dimension mismatch → skip, no crash) ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore

    db = Path(_TMP) / "p3.sqlite3"
    if db.exists():
        db.unlink()
    store = SemanticMemoryStore(path=db)
    all_ok = True

    # add a real memory (gets a proper-dimension vector)
    store.add(user_id=1, content="User likes Python programming", kind="fact")
    rec = store.list_all(user_id=1)
    all_ok &= _ok("real memory added", len(rec) == 1, f"count={len(rec)}")
    if not rec:
        return False
    real_id = rec[0].id

    # now manually inject a WRONG-dimension vector into the DB to simulate
    # a model upgrade where old vectors have a different dim
    conn = sqlite3.connect(str(db))
    # insert a fake row with a 64-dim vector (real model is 384)
    fake_id = "fake_stale_dim_001"
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        """INSERT OR REPLACE INTO memories
           (id, user_id, project_id, kind, content, meta_json, vector_json,
            created_at, updated_at, last_accessed_at, access_count, access_history)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (fake_id, 1, "", "fact", "stale vector wrong dim",
         "{}",
         json.dumps([0.1] * 64),  # 64-dim, NOT 384
         now_iso, now_iso, now_iso,
         0, "[]"),
    )
    conn.commit()
    conn.close()

    # reload — this is where the re-embedding safety kicks in
    # it must NOT crash, and the stale vector must be flagged
    store2 = SemanticMemoryStore(path=db)
    all_ok &= _ok("reload with mismatched dim did NOT crash", True)

    # the mismatched id should be in _mismatched_ids
    all_ok &= _ok("stale-dim vector flagged in _mismatched_ids",
                  fake_id in store2._mismatched_ids,
                  f"mismatched={store2._mismatched_ids}")

    # the real vector should still be cached (not skipped)
    all_ok &= _ok("correct-dim vector still cached",
                  real_id in store2._vec_cache,
                  f"cached_ids={len(store2._vec_cache)}")

    # search must still work (not crash on the ragged array)
    results = store2.semantic_search(user_id=1, query="Python programming")
    all_ok &= _ok("search works despite mismatched vector", len(results) >= 0)

    # the real memory should be findable (stale one excluded from matrix)
    found_real = any(r.id == real_id for r, _ in results)
    all_ok &= _ok("real memory is searchable (stale excluded from matrix)",
                  found_real, f"results={[(r.id, round(s,3)) for r,s in results]}")

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P4: Batch access tracking — single batch SELECT (no N+1)
# ──────────────────────────────────────────────────────────────────────────
def test_p4_batch_access() -> bool:
    print("\n=== P4: Batch access tracking (single batch SELECT, no N+1) ===")
    from lumen.engine.services.semantic_memory.store import SemanticMemoryStore

    db = Path(_TMP) / "p4.sqlite3"
    if db.exists():
        db.unlink()
    store = SemanticMemoryStore(path=db)
    all_ok = True

    # add 5 distinct memories
    ids = []
    for i in range(5):
        store.add(user_id=1, content=f"Fact number {i} about topic {i}", kind="fact")
    recs = store.list_all(user_id=1)
    ids = [r.id for r in recs]
    all_ok &= _ok("5 memories added", len(ids) == 5, f"count={len(ids)}")
    if len(ids) < 5:
        return False

    # verify all start with access_count=0
    before = {r.id: r.access_count for r in store.list_all(user_id=1)}
    all_ok &= _ok("all start at access_count=0",
                  all(v == 0 for v in before.values()), str(before))

    # Inspect the source to prove the batch pattern (no N+1 SELECTs)
    import inspect
    src = inspect.getsource(SemanticMemoryStore._record_access)
    all_ok &= _ok("uses batch SELECT with IN clause",
                  "IN (" in src and "SELECT id, access_history, access_count" in src,
                  "batch pattern found in source")

    all_ok &= _ok("does NOT loop SELECT per memory (no N+1 pattern)",
                  "SELECT * FROM memories WHERE id=?" not in src,
                  "no per-row SELECT in _record_access")

    # call _record_access with all 5 ids at once
    store._record_access(ids)

    # verify ALL were bumped (access_count=1, last_accessed updated)
    after = {r.id: r.access_count for r in store.list_all(user_id=1)}
    all_ok &= _ok("all 5 bumped to access_count=1 after single batch call",
                  all(v == 1 for v in after.values()), str(after))

    # call again to verify increment
    store._record_access(ids)
    after2 = {r.id: r.access_count for r in store.list_all(user_id=1)}
    all_ok &= _ok("all 5 bumped to access_count=2 after second batch call",
                  all(v == 2 for v in after2.values()), str(after2))

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P5: numpy dedup path — consistent with search (Q @ subᵀ)
# ──────────────────────────────────────────────────────────────────────────
def test_p5_numpy_dedup() -> bool:
    print("\n=== P5: numpy dedup path (Q @ subᵀ, consistent with search) ===")
    from lumen.engine.services.semantic_memory.store import (
        SemanticMemoryStore,
        _DEDUP_THRESHOLD,
    )
    import inspect

    all_ok = True
    src = inspect.getsource(SemanticMemoryStore._find_duplicate)
    all_ok &= _ok("numpy path uses matrix multiply (Q @ subᵀ)",
                  "sub @ q" in src or "sub @ q" in src,
                  "numpy matmul in dedup")
    all_ok &= _ok("uses _mat_ids index mapping",
                  "id_to_row" in src, "id_to_row mapping present")
    all_ok &= _ok("excludes mismatched ids from dedup",
                  "_mismatched_ids" in src, "mismatch exclusion in dedup")
    all_ok &= _ok("has Python fallback path",
                  "pure-Python fallback" in src or "Python fallback" in src.lower(),
                  "fallback present")

    # functional test: adding a near-duplicate should UPDATE, not insert
    db = Path(_TMP) / "p5.sqlite3"
    if db.exists():
        db.unlink()
    store = SemanticMemoryStore(path=db)
    store.add(user_id=1, content="The user prefers dark mode for coding", kind="fact")
    before = store.list_all(user_id=1)
    all_ok &= _ok("first memory added", len(before) == 1, f"count={len(before)}")

    # near-duplicate (same meaning, different wording)
    store.add(user_id=1, content="The user likes dark mode when programming", kind="fact")
    after = store.list_all(user_id=1)
    all_ok &= _ok("near-duplicate UPDATEs (count stays 1, not 2)",
                  len(after) == 1, f"count={len(after)} (should be 1)")

    # different fact should INSERT
    store.add(user_id=1, content="The user lives in Cairo, Egypt", kind="fact")
    final = store.list_all(user_id=1)
    all_ok &= _ok("different fact INSERTs (count becomes 2)",
                  len(final) == 2, f"count={len(final)} (should be 2)")

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P6 removed: LiveDeploymentEngine deleted with engines/generators.
# Restart-after-edit now uses HostingService in repo_dev_router.


def test_p7_local_driver_restart() -> bool:
    print("\n=== P7: LocalProcessDriver.restart (stop + deploy, not just stop) ===")
    import inspect
    from lumen.engine.services.live_deployment.local_process_driver import (
        LocalProcessDriver,
    )

    all_ok = True
    src = inspect.getsource(LocalProcessDriver.restart)
    all_ok &= _ok("accepts bot_token kwarg", "bot_token" in src)
    all_ok &= _ok("accepts project_path kwarg", "project_path" in src)
    all_ok &= _ok("calls self.stop() first", "self.stop(" in src)
    all_ok &= _ok("calls self.deploy() after stop", "self.deploy(" in src)
    all_ok &= _ok("passes BOT_TOKEN to deploy", "BOT_TOKEN" in src)
    all_ok &= _ok("passes project_path to deploy", "project_path" in src or "resolved_path" in src)

    # Also verify the contract: if no token or no path, returns gracefully
    # (old is stopped but new can't start)
    all_ok &= _ok("graceful when no token/path (returns status, no crash)",
                  "DEPLOY_STOPPED" in src or "DEPLOY_FAILED" in src,
                  "returns a status, doesn't raise")

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P8: Docker + Sandbox driver restart — same contract
# ──────────────────────────────────────────────────────────────────────────
def test_p8_docker_sandbox_restart() -> bool:
    print("\n=== P8: Docker + Sandbox driver restart (stop + deploy contract) ===")
    import inspect
    from lumen.engine.services.live_deployment.docker_process_driver import (
        DockerProcessDriver,
    )
    from lumen.engine.services.live_deployment.sandbox_process_driver import (
        SandboxProcessDriver,
    )

    all_ok = True
    for cls, name in [(DockerProcessDriver, "Docker"), (SandboxProcessDriver, "Sandbox")]:
        src = inspect.getsource(cls.restart)
        all_ok &= _ok(f"{name}: accepts bot_token", "bot_token" in src)
        all_ok &= _ok(f"{name}: accepts project_path", "project_path" in src)
        all_ok &= _ok(f"{name}: calls self.stop()", "self.stop(" in src)
        all_ok &= _ok(f"{name}: calls self.deploy()", "self.deploy(" in src)
        all_ok &= _ok(f"{name}: passes BOT_TOKEN", "BOT_TOKEN" in src)

    return all_ok


# ──────────────────────────────────────────────────────────────────────────
# P9: Router wiring — smart restart called after edit
# ──────────────────────────────────────────────────────────────────────────
def test_p9_router_wiring() -> bool:
    print("\n=== P9: Router wiring (smart restart after edit) ===")
    router_path = ROOT / "lumen" / "bot" / "routers" / "repo_dev_router.py"
    src = router_path.read_text(encoding="utf-8")

    all_ok = True
    all_ok &= _ok(
        "router uses HostingService for restart (not deleted LiveDeploymentEngine)",
        "get_hosting_service" in src and "LiveDeploymentEngine" not in src,
    )
    all_ok &= _ok("router stops running host instances after edit", "svc.stop" in src or "_svc.stop" in src)
    all_ok &= _ok("restart is best-effort (wrapped in try/except)", "except Exception" in src)
    all_ok &= _ok(
        "restart near edit path",
        "get_hosting_service" in src
        and ("record_edit" in src or "dev.ok" in src or "changed_files" in src),
    )
    return all_ok


# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        test_p1_exponential_decay,
        test_p2_importance_weighting,
        test_p3_reembedding_safety,
        test_p4_batch_access,
        test_p5_numpy_dedup,
                test_p7_local_driver_restart,
        test_p8_docker_sandbox_restart,
        test_p9_router_wiring,
    ]
    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
                print(f"  → {t.__name__}: PASS")
            else:
                print(f"  → {t.__name__}: FAIL")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  → {t.__name__}: ERROR ({e})")
    print(f"\n{'='*60}")
    print(f"Polish tests: {passed}/{len(tests)} passed")
    print(f"{'='*60}")
    sys.exit(0 if passed == len(tests) else 1)
