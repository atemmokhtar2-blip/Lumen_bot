"""Phase 9 hardened — pipeline in preflight, OCR download path, fail-safe commands."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection import (
    pipeline_trace,
    fail_safe_message,
    telegram_preflight,
    metadata_from_report,
    detect_capabilities,
)
from telegram_bot_engine.services.capability_detection.packs.loader import (
    load_all_packs,
    _LOADED_PACKS,
    _OVERLAY_KEYS,
    _KEYWORD_INDEX,
)
from telegram_bot_engine import generate_bot


def _reload():
    _LOADED_PACKS.clear()
    _OVERLAY_KEYS.clear()
    _KEYWORD_INDEX.clear()
    load_all_packs()


def test_pipeline_trace_translate_ok():
    _reload()
    tr = pipeline_trace("بوت يترجم الرسائل تلقائياً", include_research=False)
    assert tr["ok"] is True
    assert tr["detection"]["status"] in {"exists", "composable"}
    assert "scaffold_translate" in tr["detection"]["feature_keys"]
    assert tr["fail_safe"]["level"] in {"ok", "partial"}
    assert tr["fail_safe"].get("commands_ar")
    assert any("translate" in str(c) for c in tr["fail_safe"]["commands_ar"])
    msg = fail_safe_message(tr)
    assert "الحالة" in msg
    assert "أوامر" in msg


def test_pipeline_trace_impossible_blocks():
    tr = pipeline_trace("بوت يتعلم من المحادثات ويدرب نموذج ذكاء اصطناعي", include_research=False)
    assert tr["preflight"]["should_block"] is True
    assert tr["fail_safe"]["level"] == "block"


def test_preflight_includes_commands_from_trace(monkeypatch):
    _reload()
    monkeypatch.setenv("CAPABILITY_PIPELINE_TRACE", "1")
    pre = telegram_preflight("بوت يترجم الرسائل تلقائياً")
    assert pre["should_block"] is False
    assert "translate" in (pre.get("soft_note") or "")


def test_metadata_includes_fail_safe():
    _reload()
    rep = detect_capabilities("بوت ترحيب للمجموعة")
    meta = metadata_from_report(rep)
    assert "capability_detection" in meta
    assert "pipeline_fail_safe" in meta


def test_generate_ocr_includes_photo_download_path():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت OCR",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_ocr"],
        )
        assert r.success
        text = ""
        for f in Path(r.project_path).rglob("*.py"):
            text += f.read_text(encoding="utf-8", errors="ignore")
        assert "photo_router" in text
        assert "filters.PHOTO" in text
        assert "get_file" in text or "download_to_drive" in text
        assert "ocr_photo" in text or "ocr_from_image" in text
        assert "ocr_from_image" in (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
