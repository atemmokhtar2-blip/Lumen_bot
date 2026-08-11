"""Phase 8 — deterministic scaffolds for translate/OCR/schedule."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection.packs.emit_contract import (
    assess_capability,
)
from telegram_bot_engine.services.capability_detection.packs.loader import load_all_packs
from telegram_bot_engine.services.capability_detection import detect_capabilities
from telegram_bot_engine.spec_core.registry import get_capability
from telegram_bot_engine import generate_bot


def test_emit_contract_phase8_methods_safe():
    assert assess_capability("x", "translate", "translate").safe is True
    assert assess_capability("x", "ocr", "ocr_hint").safe is True
    assert assess_capability("x", "scheduler", "schedule_note").safe is True


def test_phase8_pack_loads_and_detects():
    load_all_packs()
    assert get_capability("scaffold_translate") is not None
    assert get_capability("scaffold_ocr") is not None
    assert get_capability("scaffold_schedule") is not None
    rep = detect_capabilities("بوت ترجمة تلقائية للرسائل")
    keys = {m.key for m in rep.matched}
    assert "scaffold_translate" in keys or any("translat" in k for k in keys)


def test_generate_includes_translate_scaffold():
    load_all_packs()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترجمة بسيط",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_translate"],
        )
        assert r is not None and r.success
        text = ""
        for f in Path(r.project_path).rglob("*.py"):
            text += f.read_text(encoding="utf-8", errors="ignore")
        assert "translate_text" in text or "scaffold_translate" in text
        assert (Path(r.project_path) / "app" / "services" / "generic.py").exists()


def test_generic_translate_runtime():
    src = Path("telegram_bot_engine/spec_core/templates_generic.py").read_text(encoding="utf-8")
    assert "def translate_text" in src
    assert "def ocr_hint" in src
    assert "def schedule_note" in src
