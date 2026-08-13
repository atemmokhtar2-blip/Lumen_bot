"""Phase 4 hardened — packs, emit contract, gap→pack pipeline."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    CapabilityPack,
    PackCapability,
    approve_and_register,
    assess_capability,
    detect_capabilities,
    draft_pack_from_research,
    draft_packs_from_open_gaps,
    ensure_packs_loaded,
    journal_stats,
    list_open_gaps,
    load_all_packs,
    overlay_keys,
    record_gaps,
    research_spec_from_gap,
    save_research_spec,
    telegram_preflight,
    validate_pack,
)
from telegram_bot_engine.spec_core.registry import get_capability
from telegram_bot_engine.services.capability_detection.models import GapItem


def test_example_pack_loads_and_is_emit_safe():
    load_all_packs()
    cap = get_capability("broadcast_schedule")
    assert cap is not None
    a = assess_capability(cap.key, cap.service, cap.method)
    assert a.safe is True
    assert a.level == "safe"


def test_pack_keywords_hit_extractor():
    ensure_packs_loaded()
    # force inject by reload
    load_all_packs()
    keys = detect_capabilities("بوت جدولة إذاعة جماعية")
    matched = {m.key for m in keys.matched}
    assert "broadcast_schedule" in matched or "announce" in matched


def test_reject_unsafe_service_on_approve():
    bad = CapabilityPack(
        id="bad_pack",
        capabilities=[
            PackCapability(
                key="pack_rce",
                service="hacker",
                method="rce",
                description_ar="خطر",
                description_en="danger",
            )
        ],
    )
    res = approve_and_register(bad, require_safe_emit=True)
    assert res["ok"] is False
    assert any("unknown_service" in e or "hacker" in e for e in res.get("errors") or [])


def test_approve_safe_draft_from_gap():
    rs = research_spec_from_gap("ميزة آمنة", "غير موجودة")
    pack = draft_pack_from_research(rs, service="content", method="announce")
    res = approve_and_register(pack, require_safe_emit=True, overwrite=True)
    assert res["ok"] is True
    assert get_capability(pack.capabilities[0].key) is not None


def test_gap_journal_and_draft_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    # reset journal module path by recording into new dir
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear()
    gj._LOADED = False
    record_gaps(
        request="بوت يترجم",
        gaps=[GapItem(phrase="ترجم", reason="غير مدعوم", suggested_keys=[])],
        detection_status="gap",
    )
    assert journal_stats()["open"] >= 1
    drafts = draft_packs_from_open_gaps(limit=5)
    assert drafts
    assert "draft_pack" in drafts[0]
    assert drafts[0]["research_spec"]["status"] == "draft"


def test_preflight_blocks_nonsense():
    pre = telegram_preflight("xyz random nonsense 12345")
    assert pre["should_block"] is True


def test_detection_welcome_still_ok():
    ensure_packs_loaded()
    rep = detect_capabilities("بوت ترحيب للمجموعة")
    assert rep.status.value in {"exists", "composable", "gap"}
