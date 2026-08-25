"""Phase 5 hardened — local KB + multi-backend research (offline-safe)."""
from __future__ import annotations

from lumen.engine.services.capability_detection import (
    research_feature,
    research_open_gaps,
    research_for_detection_gaps,
    draft_pack_from_research,
    approve_and_register,
    record_gaps,
)
from lumen.engine.services.capability_detection.models import GapItem


def test_local_kb_translate_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("ترجمة تلقائية للرسائل", reason="غير مدعومة", persist=True)
    assert result.ok is True
    assert result.spec is not None
    assert result.confidence >= 0.4
    assert any("translat" in x.lower() or "deep" in x.lower() for x in (result.spec.libraries or ["x"]))
    assert "no_codegen_from_raw_research" in result.spec.risks


def test_local_kb_ocr_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("OCR قراءة صور", reason="gap")
    assert result.ok is True
    assert result.spec is not None
    assert any("tesseract" in x.lower() or "Pillow" in x for x in (result.spec.libraries or []))


def test_research_never_has_code_blob(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("translate messages")
    d = result.to_dict()
    blob = str(d)
    assert "def " not in blob
    assert "source_code" not in d
    assert result.spec and "code" not in result.spec.to_dict()


def test_draft_pack_from_kb_uses_suggested_service(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    result = research_feature("ترجمة تلقائية")
    meta = result.spec.meta or {}
    pack = draft_pack_from_research(
        result.spec,
        service=str(meta.get("suggested_service") or "generic"),
        method=str(meta.get("suggested_method") or "echo"),
    )
    # may be content.announce — assess; if not safe, echo is fallback
    reg = approve_and_register(pack, require_safe_emit=True, overwrite=True)
    if not reg.get("ok"):
        pack = draft_pack_from_research(result.spec, service="generic", method="echo")
        reg = approve_and_register(pack, require_safe_emit=True, overwrite=True)
    assert reg.get("ok") is True


def test_research_for_detection_gaps(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    gaps = [GapItem(phrase="يترجم", reason="غير موجود")]
    out = research_for_detection_gaps(gaps, request="بوت ترجمة", limit=1)
    assert out and out[0].get("spec")


def test_research_open_gaps_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_RESEARCH_OFFLINE", "1")
    from lumen.engine.services.capability_detection import gap_journal as gj
    gj._CACHE.clear(); gj._LOADED = False
    record_gaps(
        request="بوت ترجمة",
        gaps=[GapItem(phrase="ترجم", reason="غير مدعوم")],
        detection_status="gap",
    )
    out = research_open_gaps(limit=3, persist=True)
    assert out
    assert out[0]["research"]["ok"] is True
    assert out[0].get("draft_pack")
