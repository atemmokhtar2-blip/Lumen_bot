"""Phase 6 — learning loop promotes gaps into KB + draft packs."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    record_gaps,
    run_learning_cycle,
    load_learned_kb,
    promote_gap_to_kb,
    bootstrap_learned_kb_into_runtime,
    research_feature,
)
from telegram_bot_engine.services.capability_detection.models import GapItem
from telegram_bot_engine.services.capability_detection.gap_journal import list_open_gaps


def test_promote_gap_creates_kb_and_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    # record twice so count>=2
    g = GapItem(phrase="ميزة تعلم تجريبية xyz", reason="غير موجودة في السجل")
    record_gaps(request="بوت ميزة تعلم تجريبية xyz", gaps=[g], detection_status="gap")
    record_gaps(request="بوت ميزة تعلم تجريبية xyz مرة ثانية", gaps=[g], detection_status="gap")
    gaps = list_open_gaps(limit=20)
    assert gaps
    target = next(x for x in gaps if "تجريبية" in x.phrase or "xyz" in x.phrase)
    res = promote_gap_to_kb(target, research=True, min_count=1)
    assert res["ok"] is True
    assert res.get("draft_pack")
    assert load_learned_kb()
    n = bootstrap_learned_kb_into_runtime()
    assert n >= 1
    # learned entry should help research
    r = research_feature("ميزة تعلم تجريبية xyz", persist=False)
    assert r.spec is not None


def test_learning_cycle_respects_min_count(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    g = GapItem(phrase="مرة واحدة فقط", reason="gap")
    record_gaps(request="مرة", gaps=[g], detection_status="gap")
    out = run_learning_cycle(min_count=5, limit=5, research=True)
    assert out["ok"] is True
    # count=1 < 5 → no promote
    assert out["promoted"] == 0
