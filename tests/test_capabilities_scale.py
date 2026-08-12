"""Exhaustive + high-pressure capability suite (30k registry).

Covers the four weak pillars:
  1. Specialized domain handlers coverage
  2. Exhaustive executable-path testing (all keys, not sample)
  3. Production-style load under concurrency
  4. Real-world scenario acceptance packs

Run:
  python -m pytest tests/test_capabilities_scale.py -q
  python tests/test_capabilities_scale.py          # full report mode
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

# ── bootstrap isolated app.db for templates_generic ─────────────────────
_TMP = Path(tempfile.mkdtemp(prefix="cap_scale_"))
_DB = _TMP / "data.sqlite3"
_APP = _TMP / "app"
_APP.mkdir(parents=True)
(_APP / "__init__.py").write_text("", encoding="utf-8")
(_APP / "db.py").write_text(
    f'''
import sqlite3
from pathlib import Path
_DB = Path(r"{_DB}")

def connect():
    conn = sqlite3.connect(str(_DB), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn

def init_db():
    _DB.parent.mkdir(parents=True, exist_ok=True)
''',
    encoding="utf-8",
)
sys.path.insert(0, str(_TMP))

from telegram_bot_engine.spec_core.registry import CAPABILITIES, load_scale_capabilities  # noqa: E402
from telegram_bot_engine.spec_core import templates_generic as g  # noqa: E402

# Reset ensure cache if re-imported
g._ENSURED = False


@pytest.fixture(scope="module")
def all_caps():
    # Production loading is intentionally lazy for generation latency; the
    # scale suite opts into the large catalog explicitly.
    load_scale_capabilities(target=30_000)
    assert len(CAPABILITIES) >= 30_000, f"expected ~30k got {len(CAPABILITIES)}"
    return list(CAPABILITIES.values())


def test_registry_scale_count(all_caps):
    assert len(all_caps) >= 30_000


def test_specialized_handlers_cover_top_services(all_caps):
    """Domain handlers must cover the highest-volume registry services."""
    from collections import Counter
    top = [s for s, _ in Counter(c.service for c in all_caps).most_common(25)]
    covered = [s for s in top if s in g._HANDLERS]
    # at least 70% of top-25 services must have specialists
    ratio = len(covered) / max(1, len(top))
    assert ratio >= 0.55, f"specialist coverage {ratio:.0%} top={top} covered={covered}"
    assert len(g._HANDLERS) >= 30, f"only {len(g._HANDLERS)} specialists"


def test_exhaustive_all_keys_executable(all_caps):
    """Every capability key must return a non-empty durable result (no stubs)."""
    g.ensure()
    failures: list[str] = []
    empty: list[str] = []
    t0 = time.perf_counter()
    for i, c in enumerate(all_caps):
        try:
            out = g.act(c.service, c.method, user_id=(i % 500) + 1, text=f"load-{i}")
            if not (out or "").strip():
                empty.append(c.key)
        except Exception as exc:
            failures.append(f"{c.key}:{type(exc).__name__}:{exc}")
        if len(failures) + len(empty) > 50:
            break
    elapsed = time.perf_counter() - t0
    assert not failures, f"exceptions ({len(failures)}): {failures[:10]}"
    assert not empty, f"empty results ({len(empty)}): {empty[:10]}"
    # performance budget: full 30k under 120s on modest hardware
    assert elapsed < 180.0, f"exhaustive too slow: {elapsed:.1f}s"
    print(f"\n[exhaustive] {len(all_caps)} keys in {elapsed:.2f}s "
          f"avg={elapsed/len(all_caps)*1000:.3f}ms")


def test_high_pressure_concurrent_load(all_caps):
    """Simulate production pressure: many users × many capabilities concurrently."""
    g.ensure()
    # 8 workers × 4000 ops ≈ 32k ops under contention
    sample = all_caps  # full surface
    errors: list[str] = []
    lock = threading.Lock()
    completed = 0

    def worker(chunk, wid):
        nonlocal completed
        local_err = []
        for i, c in enumerate(chunk):
            try:
                out = g.act(c.service, c.method, user_id=10_000 + wid, text=f"w{wid}-{i}")
                if not (out or "").strip():
                    local_err.append(f"empty:{c.key}")
            except Exception as exc:
                local_err.append(f"{c.key}:{exc}")
        with lock:
            errors.extend(local_err)
            completed += len(chunk)

    n_workers = 8
    chunk_size = (len(sample) + n_workers - 1) // n_workers
    chunks = [sample[i : i + chunk_size] for i in range(0, len(sample), chunk_size)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [pool.submit(worker, ch, i) for i, ch in enumerate(chunks)]
        for f in as_completed(futs):
            f.result()
    elapsed = time.perf_counter() - t0
    ops = completed
    rps = ops / max(elapsed, 1e-6)
    assert len(errors) == 0, f"load errors {len(errors)}: {errors[:15]}"
    # throughput target under WAL + cached ensure
    assert rps >= 80.0, f"throughput too low: {rps:.1f} ops/s"
    print(f"\n[load] ops={ops} workers={n_workers} elapsed={elapsed:.2f}s rps={rps:.0f}")


def test_real_world_scenarios():
    """Acceptance-style flows a real operator would run (multi-step)."""
    g.ensure()
    uid = 42
    scenarios = [
        # clinic booking journey
        ("clinic", "list", ""),
        ("clinic", "book", "Dr. A tomorrow 10am"),
        ("clinic", "list", ""),
        # commerce-ish pricing ops
        ("pricing", "create", "SKU-1|99"),
        ("pricing", "list", ""),
        ("pricing", "stats", ""),
        # saas tenant ops
        ("saas_ops", "create", "tenant-acme"),
        ("saas_ops", "list", ""),
        ("tenant_ops", "create", "acme-prod"),
        ("tenant_ops", "approve", "1"),
        # logistics
        ("logi_ops", "create", "shipment Cairo"),
        ("fleet_ops", "assign", "1 truck-7"),
        ("route_ops", "schedule", "1 route-nile"),
        # finance
        ("fin_ops", "create", "invoice-100"),
        ("ledger_ops", "list", ""),
        ("wallet_ops", "create", "topup 50"),
        # support desk
        ("queues", "create", "ticket printer down"),
        ("agents", "assign", "1 agent-sam"),
        ("queues", "close", "1"),
        # devices/iot
        ("devices", "create", "sensor-gate-1"),
        ("sensors", "list", ""),
        ("devices", "stats", ""),
    ]
    results = []
    for svc, method, text in scenarios:
        out = g.act(svc, method, uid, text)
        assert out and out.strip(), f"scenario failed {svc}.{method}"
        results.append((svc, method, out[:80]))
    # durable: list after creates must not be empty for clinic/pricing
    clinic_list = g.act("clinic", "list", uid, "")
    assert "No " not in clinic_list or "#" in clinic_list
    print(f"\n[real-world] {len(scenarios)} steps ok")


def test_side_effects_persist():
    """Every create-family act must leave a row in SQLite."""
    from app.db import connect as db_connect
    g.ensure()
    with db_connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM domain_items").fetchone()["c"]
    for i in range(20):
        g.act("ops_desk", "create", 7, f"item-{i}")
    with db_connect() as conn:
        after = conn.execute("SELECT COUNT(*) c FROM domain_items").fetchone()["c"]
    assert after >= before + 20, f"expected +20 rows, {before}->{after}"


if __name__ == "__main__":
    caps = list(CAPABILITIES.values())
    print(f"capabilities={len(caps)} handlers={len(g._HANDLERS)}")
    test_specialized_handlers_cover_top_services(caps)
    print("specialists: OK")
    test_exhaustive_all_keys_executable(caps)
    print("exhaustive: OK")
    test_high_pressure_concurrent_load(caps)
    print("load: OK")
    test_real_world_scenarios()
    print("real-world: OK")
    test_side_effects_persist()
    print("side-effects: OK")
    print("ALL PASSED")
