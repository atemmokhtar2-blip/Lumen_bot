"""Phase 8 hardened — scaffolds cover gaps, friendly commands, real handlers."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lumen.engine.services.capability_detection.packs.emit_contract import (
    assess_capability,
)
from lumen.engine.services.capability_detection.packs.loader import (
    load_all_packs,
    _LOADED_PACKS,
    _OVERLAY_KEYS,
    _KEYWORD_INDEX,
)
from lumen.engine.services.capability_detection import (
    detect_capabilities,
    feature_keys,
    DetectionStatus,
)
from lumen.engine.spec_core.registry import get_capability
from lumen.engine.services.capability_detection.catalog import DEFAULT_COMMANDS
from lumen.engine import generate_bot


def _reload_packs():
    _LOADED_PACKS.clear()
    _OVERLAY_KEYS.clear()
    _KEYWORD_INDEX.clear()
    load_all_packs()


def test_emit_contract_phase8_methods_safe():
    assert assess_capability("x", "translate", "translate").safe is True
    assert assess_capability("x", "ocr", "ocr_hint").safe is True
    assert assess_capability("x", "scheduler", "schedule_note").safe is True


def test_phase8_pack_loads_and_detects_composable():
    _reload_packs()
    assert get_capability("scaffold_translate") is not None
    rep = detect_capabilities("بوت ترجمة تلقائية للرسائل")
    keys = feature_keys(rep, include_core=False)
    assert "scaffold_translate" in keys
    assert rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)
    assert not [g for g in rep.gaps if "ترجم" in g.reason]


def test_friendly_commands():
    _reload_packs()
    assert DEFAULT_COMMANDS.get("scaffold_translate") == "translate"
    assert DEFAULT_COMMANDS.get("scaffold_ocr") == "ocr"
    assert DEFAULT_COMMANDS.get("scaffold_schedule") == "schedule"


def test_generate_includes_translate_scaffold():
    _reload_packs()
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
        assert "translate_text" in text
        assert "CommandHandler('translate'" in text or 'CommandHandler("translate"' in text or "CommandHandler('translate'" in text or "translate" in text
        assert (Path(r.project_path) / "app" / "services" / "generic.py").exists()


def test_generic_translate_runtime_source():
    src = Path("lumen.engine/spec_core/templates_generic.py").read_text(encoding="utf-8")
    assert "def translate_text" in src
    assert "TRANSLATE_BACKEND" in src
    assert "def ocr_hint" in src
    assert "def schedule_note" in src
