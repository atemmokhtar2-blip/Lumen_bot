"""Phase 7 hardened — promote, verify, sanitize, auto-promote."""
from __future__ import annotations

from lumen.engine.services.capability_detection import (
    CapabilityPack,
    PackCapability,
    install_pack,
    promote_draft_file,
    promote_learned_entry,
    promotion_status,
    verify_installed,
    auto_promote_ready,
    record_gaps,
    promote_gap_to_kb,
    detect_capabilities,
    feature_keys,
)
from lumen.engine.services.capability_detection.models import GapItem
from lumen.engine.spec_core.registry import get_capability


def test_install_verifies_registry_and_extractor(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    pack = CapabilityPack(
        id="phase7_verify_pack",
        capabilities=[
            PackCapability(
                key="pack_phase7_verify_tool",
                service="generic",
                method="echo",
                description_ar="تحقق تركيب",
                description_en="Verify install tool",
                category="utils",
                keywords=["تحققتركيب7", "phase7verifytool"],
            )
        ],
    )
    res = install_pack(pack, require_safe_emit=True, overwrite=True)
    assert res["ok"] is True
    assert res["verification"]["ok"] is True
    assert get_capability("pack_phase7_verify_tool") is not None
    # detection hits keyword
    rep = detect_capabilities("بوت phase7verifytool")
    assert any(m.key == "pack_phase7_verify_tool" for m in rep.matched)


def test_sanitize_unsafe_to_echo(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    pack = CapabilityPack(
        id="evil_sanitize",
        capabilities=[
            PackCapability(
                key="pack_evil_sanitize",
                service="hacker",
                method="rce",
                description_ar="خطر",
                description_en="danger",
                keywords=["sanitizeevilkw"],
            )
        ],
    )
    res = install_pack(pack, require_safe_emit=True, overwrite=True, sanitize=True)
    assert res["ok"] is True
    assert res.get("sanitized") is True
    cap = get_capability("pack_evil_sanitize")
    assert cap is not None
    assert cap.service == "generic" and cap.method == "echo"


def test_promote_learned_and_generate_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    monkeypatch.setenv("CAPABILITY_LEARNING_AUTO", "0")
    monkeypatch.setenv("CAPABILITY_AUTO_PROMOTE", "0")
    from lumen.engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    g = GapItem(phrase="ميزة ترويج قوية", reason="غير موجودة في السجل")
    record_gaps(request="بوت ميزة ترويج قوية للاختبار", gaps=[g], detection_status="gap")
    from lumen.engine.services.capability_detection.gap_journal import list_open_gaps
    gap = list_open_gaps(limit=10)[0]
    learned = promote_gap_to_kb(gap, research=True, min_count=1)
    assert learned["ok"]
    promo = promote_learned_entry(learned["entry"]["id"], require_safe_emit=True)
    assert promo["ok"] is True
    assert promo["verification"]["ok"] is True
    keys = promo.get("registered") or []
    assert keys and get_capability(keys[0]) is not None
    # detect request
    rep = detect_capabilities("بوت ميزة ترويج قوية للاختبار")
    feats = feature_keys(rep, include_core=False)
    assert keys[0] in feats or any(m.key == keys[0] for m in rep.matched)


def test_auto_promote_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_AUTO_PROMOTE", "0")
    res = auto_promote_ready()
    assert res.get("skipped") is True
