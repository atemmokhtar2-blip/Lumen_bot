"""Phase 12 JobQueue emission + Phase 13 ops commands."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection.packs.loader import (
    load_all_packs, _LOADED_PACKS, _OVERLAY_KEYS, _KEYWORD_INDEX,
)
from telegram_bot_engine.services.capability_detection.ops import handle_ops_command
from telegram_bot_engine import generate_bot


def _reload():
    _LOADED_PACKS.clear(); _OVERLAY_KEYS.clear(); _KEYWORD_INDEX.clear()
    load_all_packs()


def test_generate_schedule_includes_jobqueue():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت تذكير مجدول",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_schedule"],
        )
        assert r.success
        main = (Path(r.project_path) / "main.py").read_text(encoding="utf-8")
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "list_due_reminders" in gen
        assert "mark_reminder_fired" in gen
        assert "_parse_due_seconds" in gen or "due_ts" in gen
        assert "run_repeating" in main or "due_reminders" in main
        assert "_fire_due_reminders" in main


def test_ops_health_and_help():
    _reload()
    help_txt = handle_ops_command("/cap_help")
    assert help_txt and "cap_health" in help_txt
    health = handle_ops_command("/cap_health")
    assert health and ("صحة" in health or "فحص" in health)
    trace = handle_ops_command("/cap_trace بوت ترحيب")
    assert trace and "الحالة" in trace
    learn = handle_ops_command("/cap_learn")
    assert learn and "تعلم" in learn
    promo = handle_ops_command("/cap_promote")
    assert promo and "ترقية" in promo
    assert handle_ops_command("not a command") is None
