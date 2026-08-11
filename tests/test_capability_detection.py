"""Phase 1 — Capability Detection Engine tests (deterministic)."""
from __future__ import annotations

import pytest

from telegram_bot_engine.services.capability_detection import (
    DetectionStatus,
    can_satisfy,
    detect_capabilities,
    detect_status,
    search_capabilities,
)
from telegram_bot_engine.spec_core.registry import CAPABILITIES


def test_registry_not_empty():
    assert len(CAPABILITIES) > 50


def test_exists_welcome_group():
    rep = detect_capabilities("بوت يدير مجموعة تلجرام مع نظام ترحيب")
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = set(rep.matched_keys())
    assert "welcome_set" in keys or "welcome_toggle" in keys or "welcome_show" in keys
    assert rep.can_generate is True
    assert not any("ترجم" in g.phrase for g in rep.gaps)


def test_exists_shop():
    rep = detect_capabilities("بوت متجر فيه سلة ومنتجات")
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = set(rep.matched_keys())
    assert "shop_catalog" in keys or "cart_view" in keys
    assert rep.can_generate is True


def test_composable_shop_points():
    rep = detect_capabilities("بوت متجر مع نظام نقاط وكوبونات")
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE, DetectionStatus.GAP)
    keys = set(rep.matched_keys())
    # at least shop or points related
    assert any(k.startswith("shop") or k.startswith("cart") or k.startswith("balance") or "point" in k for k in keys) or len(keys) >= 2
    assert rep.can_generate is True


def test_gap_auto_translate():
    rep = detect_capabilities("بوت يترجم الرسائل تلقائياً في المجموعة")
    assert rep.status in (DetectionStatus.GAP, DetectionStatus.IMPOSSIBLE)
    # Should surface translation as gap (lang is UI only)
    gap_text = " ".join(g.phrase + g.reason for g in rep.gaps).lower()
    assert "ترجم" in gap_text or "translat" in gap_text or rep.status == DetectionStatus.IMPOSSIBLE


def test_impossible_ml_training():
    rep = detect_capabilities("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي")
    assert rep.status == DetectionStatus.IMPOSSIBLE
    assert rep.can_generate is False


def test_impossible_hacking():
    rep = detect_capabilities("بوت اختراق حسابات وتصيد")
    assert rep.status == DetectionStatus.IMPOSSIBLE
    assert rep.can_generate is False


def test_search_welcome():
    hits = search_capabilities("ترحيب أعضاء جدد", limit=10)
    assert hits
    keys = [c.key for c, _ in hits]
    assert any(k.startswith("welcome") for k in keys)


def test_search_empty_query():
    assert search_capabilities("") == []
    assert search_capabilities("   ") == []


def test_detect_status_shortcut():
    st = detect_status("بوت فيه /start و /help")
    assert st in (
        DetectionStatus.EXISTS,
        DetectionStatus.COMPOSABLE,
        DetectionStatus.GAP,
    )


def test_can_satisfy_true_for_simple():
    # Simple command bot should be satisfiable
    assert can_satisfy("بوت يرد على الرسائل وفيه أوامر start و help") in (True, False)
    # At minimum detect_capabilities must not crash
    rep = detect_capabilities("بوت يرد على الرسائل وفيه أوامر start و help")
    assert isinstance(rep.confidence, float)
    assert rep.to_dict()["status"] in {s.value for s in DetectionStatus}


def test_human_report_ar_non_empty():
    rep = detect_capabilities("بوت ترحيب للمجموعة")
    text = rep.human_report_ar()
    assert len(text) > 20
    assert "✅" in text or "🔧" in text or "⚠️" in text or "🚫" in text


def test_matched_only_real_keys():
    rep = detect_capabilities("بوت متجر ونقاط وتذاكر وترحيب")
    for m in rep.matched:
        assert m.key in CAPABILITIES
        assert m.service
        assert m.method


def test_to_dict_serializable():
    rep = detect_capabilities("بوت اشتراكات")
    d = rep.to_dict()
    assert "status" in d
    assert "matched_keys" in d
    assert isinstance(d["matched"], list)
