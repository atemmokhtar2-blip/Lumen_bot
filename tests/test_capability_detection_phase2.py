"""Phase 2 — detection integration with generation preflight."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    DetectionStatus,
    apply_detection_to_session,
    feature_keys,
    metadata_from_report,
    run_detection,
    telegram_preflight,
)
from telegram_bot_engine.spec_core.builder import BuilderSession


def test_preflight_blocks_impossible():
    pre = telegram_preflight("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي")
    assert pre["should_block"] is True
    assert pre["user_message"]
    assert "لا أستطيع" in pre["user_message"] or "خارج" in pre["user_message"]


def test_preflight_blocks_pure_gap():
    pre = telegram_preflight("بوت يترجم الرسائل تلقائياً فقط بدون أي ميزة أخرى")
    assert pre["should_block"] is True
    assert pre["report"].status == DetectionStatus.GAP


def test_preflight_allows_welcome():
    pre = telegram_preflight("بوت ترحيب للمجموعة مع قوانين")
    assert pre["should_block"] is False
    assert pre["report"].status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = feature_keys(pre["report"], include_core=False)
    assert "welcome_set" in keys or "rules" in keys
    assert pre["soft_note"]


def test_preflight_partial_gap_note():
    # translate + welcome: may be gap with or without features
    pre = telegram_preflight("بوت ترحيب للمجموعة ويترجم الرسائل تلقائياً")
    assert pre["report"].status in (DetectionStatus.GAP, DetectionStatus.COMPOSABLE)
    if pre["should_block"]:
        assert pre["user_message"]
    else:
        # partial generation path
        assert "welcome_set" in feature_keys(pre["report"], include_core=False) or pre["soft_note"]


def test_apply_detection_to_session():
    session = BuilderSession(user_id=0)
    report = run_detection("بوت متجر فيه سلة")
    added = apply_detection_to_session(session, report)
    assert "start" in session.selected or "shop_catalog" in session.selected or added
    assert any(k in session.selected for k in feature_keys(report))


def test_metadata_from_report():
    report = run_detection("بوت تذاكر دعم")
    meta = metadata_from_report(report)
    assert "capability_detection" in meta
    assert meta["capability_detection"]["status"] in {s.value for s in DetectionStatus}


def test_generate_bot_signature_accepts_preferred_keys():
    import inspect
    from telegram_bot_engine import generate_bot
    sig = inspect.signature(generate_bot)
    assert "preferred_keys" in sig.parameters
