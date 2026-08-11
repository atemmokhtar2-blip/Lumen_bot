"""Phase 5 — web research produces ResearchSpec only (offline-safe)."""
from __future__ import annotations

from telegram_bot_engine.services.capability_detection import (
    research_feature,
    research_open_gaps,
    draft_pack_from_research,
    approve_and_register,
)
from telegram_bot_engine.services.capability_detection.models import GapItem
from telegram_bot_engine.services.capability_detection import record_gaps


def test_research_offline_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("ترجمة تلقائية", reason="غير مدعومة", persist=True)
    assert result.spec is not None
    assert result.spec.status == "draft"
    assert "no_codegen_from_raw_research" in result.spec.risks
    assert result.source in {"web_offline", "web_empty", "web"}


def test_research_never_returns_code_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("image OCR bot", reason="gap")
    d = result.to_dict()
    assert "code" not in d
    assert "source_code" not in d
    if result.spec:
        assert not hasattr(result.spec, "code")
        sd = result.spec.to_dict()
        assert "code" not in sd


def test_draft_pack_from_research_requires_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("ميزة بحث", reason="test")
    pack = draft_pack_from_research(result.spec, service="generic", method="echo")
    # echo is known-safe
    reg = approve_and_register(pack, require_safe_emit=True, overwrite=True)
    assert reg.get("ok") is True


def test_research_open_gaps_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    from telegram_bot_engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    record_gaps(
        request="بوت ترجمة",
        gaps=[GapItem(phrase="ترجم", reason="غير مدعوم")],
        detection_status="gap",
    )
    out = research_open_gaps(limit=3, persist=True)
    assert out
    assert out[0].get("research")
    assert out[0].get("draft_pack")
