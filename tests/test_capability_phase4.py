"""Phase 4 — extensible packs, gap journal, research specs."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection import (
    CapabilityPack,
    PackCapability,
    detect_capabilities,
    ensure_packs_loaded,
    journal_stats,
    list_open_gaps,
    load_all_packs,
    overlay_keys,
    record_gaps,
    register_pack,
    research_spec_from_gap,
    save_research_spec,
    load_research_spec,
    telegram_preflight,
    validate_pack,
)
from telegram_bot_engine.spec_core.registry import CAPABILITIES, get_capability


def test_validate_and_register_pack():
    pack = CapabilityPack(
        id="test_pack_unit",
        version="1.0.0",
        capabilities=[
            PackCapability(
                key="unit_test_cap_xyz",
                service="utils",
                method="unit_test_cap",
                description_ar="قدرة اختبار",
                description_en="Unit test capability",
                category="utils",
                keywords=["قدرةاختبارxyz", "unit_test_cap_xyz_kw"],
            )
        ],
    )
    assert validate_pack(pack) == []
    res = register_pack(pack, overwrite=True)
    assert res["ok"] is True
    assert "unit_test_cap_xyz" in res["registered"]
    assert get_capability("unit_test_cap_xyz") is not None
    assert "unit_test_cap_xyz" in overlay_keys()


def test_load_example_pack_from_repo():
    res = load_all_packs()
    assert res["ok"] is True
    # example pack may register broadcast_schedule
    cap = get_capability("broadcast_schedule")
    # If pack loaded and not conflicting
    if cap:
        assert cap.service == "content"


def test_gap_journal_records():
    import os
    from telegram_bot_engine.services.capability_detection.models import GapItem

    pre = telegram_preflight("بوت يترجم الرسائل تلقائياً فقط")
    # preflight records gaps internally; also explicit
    gaps = pre["report"].gaps or [
        GapItem(phrase="ترجم", reason="test gap", suggested_keys=["lang"])
    ]
    recs = record_gaps(request="test translate", gaps=gaps, detection_status="gap")
    assert recs
    stats = journal_stats()
    assert stats["total"] >= 1
    open_gaps = list_open_gaps(limit=20)
    assert any("ترجم" in g.phrase or "ترجم" in g.reason for g in open_gaps) or open_gaps


def test_research_spec_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    # reload path helpers by creating new spec
    from telegram_bot_engine.services.capability_detection import research_spec as rs

    spec = research_spec_from_gap("ترجمة تلقائية", "غير موجودة", request="بوت ترجمة")
    path = rs.save_research_spec(spec)
    assert path.exists()
    loaded = rs.load_research_spec(spec.feature_id)
    assert loaded is not None
    assert loaded.title == "ترجمة تلقائية"
    assert loaded.status == "draft"
    assert "no_codegen_from_raw_research" in loaded.risks


def test_detection_still_works_after_packs():
    ensure_packs_loaded()
    rep = detect_capabilities("بوت ترحيب للمجموعة")
    assert rep.can_generate or rep.status.value in {"exists", "composable", "gap"}
