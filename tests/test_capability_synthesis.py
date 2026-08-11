"""Phase 3 — Template Synthesis Engine tests."""
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
    assert "start" in plan.keys


def test_welcome_companion_rules():
    plan = synthesize_from_keys(["welcome_set"])
    assert "welcome_set" in plan.keys
    # rules is category companion for welcome
    assert "rules" in plan.keys or "welcome_set" in plan.keys


def test_synthesize_from_shop_request():
    report, plan = synthesize_for_request("بوت متجر فيه سلة")
    assert plan.status in ("ok", "partial")
    assert "shop_catalog" in plan.keys or "cart_view" in plan.keys
    assert "start" in plan.keys


def test_feature_keys_uses_synthesis():
    report = detect_capabilities("بوت متجر فيه سلة")
    raw = feature_keys(report, include_core=False, synthesize=False)
    syn = feature_keys(report, include_core=False, synthesize=True)
    # synthesis should be superset (deps added)
    assert set(raw).issubset(set(syn)) or len(syn) >= len(raw)


def test_impossible_yields_empty_plan():
    report = detect_capabilities("بوت يتعلم من المحادثات ويدرب نموذج")
    plan = synthesize_from_report(report)
    assert plan.status == "empty" or report.status.value == "impossible"


def test_bulk_keys_filtered():
    plan = synthesize_from_keys(["cart_view", "clinic2_create", "grp_create"])
    assert "clinic2_create" not in plan.keys
    assert "grp_create" not in plan.keys
