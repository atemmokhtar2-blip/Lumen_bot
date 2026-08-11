"""Phase 10 — system health + generated project smoke."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection import (
    capability_system_health,
    smoke_generated_project,
    attach_generation_diagnostics,
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


def test_capability_system_health_ok():
    _reload()
    h = capability_system_health()
    assert h["ok"] is True
    assert h["failed"] == 0
    names = {c["name"] for c in h["checks"]}
    assert any(n.startswith("scaffold:scaffold_translate") for n in names)
    assert any(n.startswith("detect_translate") for n in names)


def test_smoke_generated_translate_project():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترجمة",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_translate"],
        )
        assert r.success
        smoke = smoke_generated_project(
            r.project_path,
            expected_keys=["start", "help", "scaffold_translate"],
        )
        assert smoke["ok"] is True, smoke.get("errors")
        assert smoke["failed"] == 0


def test_diagnostics_attached_on_generate():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت ترحيب",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "welcome_set"],
        )
        assert r.success
        diag = (r.metadata or {}).get("capability_diagnostics")
        assert diag is not None
        assert diag.get("system_health", {}).get("ok") is True
        assert "pipeline" in diag
