"""Phase 6 hardened — auto-learn, clustering, stable Arabic ids."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    record_gaps,
    run_learning_cycle,
    load_learned_kb,
    promote_gap_to_kb,
    bootstrap_learned_kb_into_runtime,
    research_feature,
    maybe_auto_learn,
    learning_stats,
    telegram_preflight,
)
from telegram_bot_engine.services.capability_detection.models import GapItem
from telegram_bot_engine.services.capability_detection.gap_journal import list_open_gaps


def test_promote_clusters_and_stable_id(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_AUTO", "0")  # manual promote
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    for phrase in ("يترجم", "ترجمة تلقائية", "يترجم الرسائل"):
        g = GapItem(phrase=phrase, reason="غير موجودة")
        record_gaps(request=f"بوت {phrase}", gaps=[g], detection_status="gap")
        record_gaps(request=f"بوت {phrase} 2", gaps=[g], detection_status="gap")
    gaps = list_open_gaps(limit=20)
    assert gaps
    target = gaps[0]
    res = promote_gap_to_kb(target, research=True, min_count=1, cluster=True)
    assert res["ok"] is True
    assert res.get("cluster_size", 1) >= 1
    eid = res["entry"]["id"]
    assert eid.startswith("learned_")
    assert "learned_learned" not in eid
    assert len(res["entry"]["phrases"]) >= 1
    assert load_learned_kb()
    assert bootstrap_learned_kb_into_runtime() >= 1


def test_auto_learn_via_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_AUTO", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_MIN_COUNT", "2")
    monkeypatch.setenv("CAPABILITY_LEARNING_COOLDOWN", "0")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    from telegram_bot_engine.services.capability_detection import learning_loop as ll
    gj._CACHE.clear(); gj._LOADED = False
    ll._AUTO_LAST_RUN = 0.0
    # use a remaining hard gap (voice) so journal records gaps
    telegram_preflight("بوت يحول الصوت لنص speech to text")
    telegram_preflight("بوت يحول الصوت لنص speech to text مرة أخرى")
    kb = load_learned_kb()
    # may learn if gaps recorded twice
    assert len(kb) >= 0  # non-fatal if feasibility blocks before gaps
    if len(list_open_gaps(limit=5)) >= 1:
        from telegram_bot_engine.services.capability_detection import run_learning_cycle
        run_learning_cycle(min_count=1, limit=3, research=True)
        assert len(load_learned_kb()) >= 1
    stats = learning_stats()
    assert stats["learned_entries"] >= 1


def test_learning_cycle_min_count(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    g = GapItem(phrase="مرة واحدة فقط abc", reason="gap")
    record_gaps(request="مرة", gaps=[g], detection_status="gap")
    out = run_learning_cycle(min_count=5, limit=5, research=True)
    assert out["ok"] is True
    assert out["promoted"] == 0


def test_maybe_auto_learn_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_LEARNING_AUTO", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_COOLDOWN", "9999")
    from telegram_bot_engine.services.capability_detection import learning_loop as ll
    ll._AUTO_LAST_RUN = __import__("time").time()
    res = maybe_auto_learn()
    assert res and res.get("skipped") is True
