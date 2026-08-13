"""Phase 3 — Template Synthesis Engine tests (hardened)."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    detect_capabilities,
    feature_keys,
    synthesize_from_keys,
    synthesize_from_report,
    synthesize_for_request,
)


def test_cart_pulls_shop_dependency():
    plan = synthesize_from_keys(["cart_view", "start", "help"])
    assert "shop_catalog" in plan.keys
    assert "cart_view" in plan.keys
    assert "shop_catalog" in plan.added_dependencies


def test_draw_winner_pulls_contests():
    plan = synthesize_from_keys(["draw_winner"])
    assert "contests" in plan.keys


def test_welcome_companion_rules():
    plan = synthesize_from_keys(["welcome_set"], request="بوت ترحيب")
    assert "welcome_set" in plan.keys
    assert "rules" in plan.keys


def test_shop_request_no_contest_noise():
    report, plan = synthesize_for_request("بوت متجر فيه سلة وكوبونات")
    assert "shop_catalog" in plan.keys or "cart_view" in plan.keys
    assert "contests" not in plan.keys
    assert "join_contest" not in plan.keys
    assert "draw_winner" not in plan.keys
    assert "achievement_list" not in plan.keys


def test_points_shop_referral_clean():
    report, plan = synthesize_for_request("متجر مع إحالة ونقاط")
    assert "shop_catalog" in plan.keys or "balance" in plan.keys or "referral_code" in plan.keys
    assert "contests" not in plan.keys
    assert "join_contest" not in plan.keys


def test_salon_booking_no_tickets_noise():
    report, plan = synthesize_for_request("عايز بوت حجوزات لصالون تجميل")
    assert "book_slot" in plan.keys or "clinic_book" in plan.keys
    assert "ticket_open" not in plan.keys
    assert "note_add" not in plan.keys


def test_moderation_pack():
    report, plan = synthesize_for_request("بوت إدارة جروب حظر وكتم وطرد")
    assert "user_ban" in plan.keys
    assert "user_mute" in plan.keys
    assert "user_kick" in plan.keys


def test_feature_keys_uses_synthesis():
    report = detect_capabilities("بوت متجر فيه سلة")
    syn = feature_keys(report, include_core=False, synthesize=True)
    assert "shop_catalog" in syn or "cart_view" in syn


def test_impossible_yields_empty_plan():
    report = detect_capabilities("بوت يتعلم من المحادثات ويدرب نموذج")
    plan = synthesize_from_report(report)
    assert plan.status == "empty" or len(plan.keys) == 0


def test_bulk_keys_filtered():
    plan = synthesize_from_keys(["cart_view", "clinic2_create", "grp_create"])
    assert "clinic2_create" not in plan.keys
    assert "grp_create" not in plan.keys


def test_lang_pruned_without_hint():
    plan = synthesize_from_keys(
        ["shop_catalog", "lang"],
        request="بوت متجر منتجات",
    )
    assert "shop_catalog" in plan.keys
    assert "lang" not in plan.keys


def test_pack_size_capped():
    many = [
        "shop_catalog", "cart_view", "coupon_apply", "balance", "leaderboard",
        "ticket_open", "plans", "welcome_set", "user_ban", "user_mute",
        "user_kick", "contests", "draw_winner", "book_slot", "echo",
        "faq_show", "poll_create", "referral_code",
    ]
    plan = synthesize_from_keys(many, request="بوت متجر ونقاط وتذاكر وترحيب ومسابقات وحجز")
    assert len(plan.keys) <= 14 + 2  # core may pad
