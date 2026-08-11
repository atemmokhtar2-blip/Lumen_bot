"""Phase 10 hardened — strict smoke, command registration, health log."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection import (
    capability_system_health,
    smoke_generated_project,
    attach_generation_diagnostics,
    health_summary_ar,
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
    assert h["critical_failed"] == 0
    assert health_summary_ar(h).startswith("✅")


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
        assert smoke["critical_failed"] == 0
        names = {c["name"] for c in smoke["checks"]}
        assert any(n.startswith("command_registered:") for n in names)
        assert "scaffold_translate_runtime" in names


def test_diagnostics_attached_on_generate(tmp_path, monkeypatch):
    _reload()
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CAPABILITY_HEALTH_LOG", "1")
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
        # log written
        log = tmp_path / "platform" / "health" / "system_health_last.json"
        assert log.exists() or diag.get("system_health", {}).get("log_path")


def test_smoke_detects_broken_project(tmp_path):
    root = tmp_path / "broken_bot"
    root.mkdir()
    (root / "main.py").write_text("def broken(\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "handlers.py").write_text("x = 1\n", encoding="utf-8")
    (root / "app" / "config.py").write_text("x = 1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("python-telegram-bot==21.6\n", encoding="utf-8")
    smoke = smoke_generated_project(root, expected_keys=["scaffold_translate"])
    assert smoke["ok"] is False
    assert smoke["critical_failed"] >= 1


def test_strict_smoke_can_flag_fail_build(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPABILITY_SMOKE_STRICT", "1")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    root = tmp_path / "broken_bot"
    root.mkdir()
    (root / "main.py").write_text("def broken(\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "handlers.py").write_text("x=1\n", encoding="utf-8")
    (root / "app" / "config.py").write_text("x=1\n", encoding="utf-8")
    (root / "requirements.txt").write_text("python-telegram-bot==21.6\n", encoding="utf-8")
    diag = attach_generation_diagnostics(
        request="test",
        project_path=root,
        preferred_keys=["scaffold_translate"],
    )
    assert diag["should_fail_build"] is True
