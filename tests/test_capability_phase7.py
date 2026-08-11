"""Phase 7 — promote draft/learned packs into installable registry packs."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    CapabilityPack,
    PackCapability,
    install_pack,
    promote_draft_file,
    promote_learned_entry,
    promote_latest_drafts,
    promotion_status,
    record_gaps,
    promote_gap_to_kb,
    load_learned_kb,
    detect_capabilities,
)
from telegram_bot_engine.services.capability_detection.models import GapItem
from telegram_bot_engine.spec_core.registry import get_capability


def test_install_safe_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    pack = CapabilityPack(
        id="phase7_test_pack",
        capabilities=[
            PackCapability(
                key="pack_phase7_echo_tool",
                service="generic",
                method="echo",
                description_ar="أداة اختبار",
                description_en="Phase7 test tool",
                category="utils",
                keywords=["phase7toolxyz", "أداةاختبار7"],
            )
        ],
    )
    res = install_pack(pack, require_safe_emit=True, overwrite=True)
    assert res["ok"] is True
    assert get_capability("pack_phase7_echo_tool") is not None
    assert (tmp_path / "platform" / "capability_packs" / "phase7_test_pack.json").exists()
    st = promotion_status()
    assert st["installed_packs"] >= 1


def test_reject_unsafe_install(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    pack = CapabilityPack(
        id="evil7",
        capabilities=[
            PackCapability(
                key="pack_evil7",
                service="hacker",
                method="rce",
                description_ar="x",
                description_en="x",
            )
        ],
    )
    res = install_pack(pack, require_safe_emit=True)
    assert res["ok"] is False


def test_promote_learned_entry_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_AUTO", "0")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    g = GapItem(phrase="ميزة ترويج سبعة", reason="غير موجودة")
    record_gaps(request="بوت ميزة ترويج سبعة", gaps=[g], detection_status="gap")
    record_gaps(request="بوت ميزة ترويج سبعة 2", gaps=[g], detection_status="gap")
    from telegram_bot_engine.services.capability_detection.gap_journal import list_open_gaps
    gap = list_open_gaps(limit=10)[0]
    learned = promote_gap_to_kb(gap, research=True, min_count=1)
    assert learned["ok"]
    entry_id = learned["entry"]["id"]
    promo = promote_learned_entry(entry_id, require_safe_emit=True)
    assert promo["ok"] is True
    # registered key should exist
    keys = promo.get("registered") or []
    assert keys
    assert get_capability(keys[0]) is not None


def test_promote_draft_fallback_to_echo(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    import json
    from pathlib import Path
    draft_dir = tmp_path / "platform" / "learning"
    draft_dir.mkdir(parents=True)
    draft = {
        "id": "draft_unsafe_methods",
        "version": "0.1.0",
        "capabilities": [
            {
                "key": "pack_needs_fallback",
                "service": "hacker",
                "method": "rce",
                "description_ar": "خطر",
                "description_en": "danger",
                "keywords": ["fallbacktestkw"],
            }
        ],
    }
    path = draft_dir / "draft_unsafe.json"
    path.write_text(json.dumps(draft), encoding="utf-8")
    res = promote_draft_file(path, require_safe_emit=True)
    assert res["ok"] is True
    assert res.get("fallback_to_echo") is True
