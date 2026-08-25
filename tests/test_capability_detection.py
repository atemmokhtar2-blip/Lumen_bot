"""Phase 1 — Capability Detection Engine tests (hardened)."""
from __future__ import annotations

import pytest

from lumen.engine.services.capability_detection import (
    DetectionStatus,
    can_satisfy,
    detect_capabilities,
    detect_status,
    search_capabilities,
)
from lumen.engine.services.capability_detection.search import is_bulk_key
from lumen.engine.spec_core.registry import CAPABILITIES


def test_registry_not_empty():
    assert len(CAPABILITIES) > 50


def test_welcome_group():
    rep = detect_capabilities("بوت يدير مجموعة تلجرام مع نظام ترحيب")
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = set(rep.matched_keys())
    assert "welcome_set" in keys
    assert "start" in keys
    assert rep.can_generate is True
    assert not any(is_bulk_key(k) for k in keys)


def test_welcome_with_verify():
    rep = detect_capabilities("بوت ترحيب للأعضاء الجدد مع تحقق")
    keys = set(rep.matched_keys())
    assert "welcome_set" in keys
    assert "verify_start" in keys


def test_moderation_ban_mute():
    rep = detect_capabilities("عايز بوت يشرف على الجروب يحظر ويكتم")
    keys = set(rep.matched_keys())
    assert "user_ban" in keys
    assert "user_mute" in keys


def test_shop_cart():
    rep = detect_capabilities("بوت متجر فيه سلة ومنتجات")
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    keys = set(rep.matched_keys())
    assert "shop_catalog" in keys or "cart_view" in keys
    assert not any(k.startswith("clinic2_") or k.startswith("grp_") for k in keys)


def test_shop_coupons_points():
    rep = detect_capabilities("بوت متجر مع سلة وكوبونات ونقاط")
    keys = set(rep.matched_keys())
    assert "shop_catalog" in keys or "cart_view" in keys
    assert "coupon_apply" in keys or any("point" in k or k == "balance" for k in keys)


def test_contests_draw():
    rep = detect_capabilities("بوت مسابقات وسحب فائزين")
    keys = set(rep.matched_keys())
    assert "contests" in keys or "draw_winner" in keys
    assert len(keys) >= 1
    assert rep.status != DetectionStatus.GAP or len(keys) > 0


def test_booking_clinic():
    rep = detect_capabilities("بوت حجوزات مواعيد عيادة")
    keys = set(rep.matched_keys())
    assert "book_slot" in keys or "clinic_book" in keys
    assert not any(k.startswith("clinic2_") for k in keys)


def test_echo_auto_reply():
    rep = detect_capabilities("بوت رد آلي على الرسائل فقط")
    keys = set(rep.matched_keys())
    assert "echo" in keys
    assert not any("reply" in k and k != "echo" for k in keys if k.startswith(("album_", "artist_", "blog_")))


def test_tickets_subs():
    rep = detect_capabilities("بوت فيه تذاكر دعم واشتراكات")
    keys = set(rep.matched_keys())
    assert "ticket_open" in keys
    assert "plans" in keys or "subscribe" in keys


def test_gap_auto_translate():
    # Phase 8: covered by scaffold_translate → COMPOSABLE, no translate gap
    rep = detect_capabilities("بوت يترجم الرسائل تلقائياً في المجموعة")
    assert "scaffold_translate" in set(rep.matched_keys())
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    assert not any("ترجم" in g.reason for g in rep.gaps)


def test_gap_image_ai():
    # OCR scaffold covers image-text; pure generative vision may still gap
    rep = detect_capabilities("بوت تحليل صور بالذكاء الاصطناعي")
    keys = set(rep.matched_keys())
    if "scaffold_ocr" in keys:
        assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE, DetectionStatus.GAP)
    else:
        assert rep.status in (DetectionStatus.GAP, DetectionStatus.IMPOSSIBLE)


def test_impossible_ml_training():
    rep = detect_capabilities("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي")
    assert rep.status == DetectionStatus.IMPOSSIBLE
    assert rep.can_generate is False


def test_impossible_hacking():
    rep = detect_capabilities("بوت اختراق حسابات وتصيد")
    assert rep.status == DetectionStatus.IMPOSSIBLE
    assert rep.can_generate is False


def test_zero_match_is_gap_not_composable():
    """Classification must not return COMPOSABLE with zero keys."""
    rep = detect_capabilities("xyzzy foobar quux nonexistent feature 999")
    if not rep.matched_keys():
        assert rep.status in (DetectionStatus.GAP, DetectionStatus.IMPOSSIBLE)


def test_search_welcome_primary():
    hits = search_capabilities("ترحيب أعضاء جدد", limit=10, primary_only=True)
    assert hits
    keys = [c.key for c, _ in hits]
    assert any(k.startswith("welcome") for k in keys)
    assert not any(k.startswith("grp_") for k in keys)


def test_search_empty_query():
    assert search_capabilities("") == []
    assert search_capabilities("   ") == []


def test_detect_status_shortcut():
    st = detect_status("بوت فيه /start و /help")
    assert st in list(DetectionStatus)


def test_human_report_ar_non_empty():
    rep = detect_capabilities("بوت ترحيب للمجموعة")
    text = rep.human_report_ar()
    assert len(text) > 20
    assert any(s in text for s in ("✅", "🔧", "⚠️", "🚫"))


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


def test_can_satisfy_welcome():
    assert can_satisfy("بوت ترحيب للمجموعة") is True


def test_can_satisfy_translate_false():
    # Phase 8: translate scaffold makes this satisfyable
    assert can_satisfy("بوت يترجم الرسائل تلقائياً") is True


def test_dialect_welcome_jadad():
    rep = detect_capabilities("عايز بوت للجروب يرحب بالاعضاء الجداد ويعطيهم قوانين")
    keys = set(rep.matched_keys())
    assert "welcome_set" in keys
    assert "rules" in keys


def test_salon_booking():
    rep = detect_capabilities("عايز بوت حجوزات لصالون تجميل")
    keys = set(rep.matched_keys())
    assert "book_slot" in keys or "clinic_book" in keys


def test_currency_convert():
    rep = detect_capabilities("بوت يحول العملات")
    assert "currency_convert" in rep.matched_keys()


def test_poll_create():
    rep = detect_capabilities("بوت استبيانات وتصويت")
    assert "poll_create" in rep.matched_keys()


def test_broadcast_group():
    rep = detect_capabilities("بوت يبعت رسائل جماعية للاعضاء")
    keys = set(rep.matched_keys())
    assert "broadcast_admin" in keys or "announce" in keys
    assert "purge" not in keys


def test_translate_no_noise_keys():
    rep = detect_capabilities("بوت يترجم من عربي لانجليزي تلقائي لكل رسالة")
    keys = [k for k in rep.matched_keys() if k not in ("start", "help", "lang")]
    assert "scaffold_translate" in keys
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    assert not rep.gaps  # covered by scaffold
    noise = [k for k in keys if k not in {"scaffold_translate", "lang"}]
    assert not any(k.startswith("clinic") or k.startswith("grp_") for k in noise)
