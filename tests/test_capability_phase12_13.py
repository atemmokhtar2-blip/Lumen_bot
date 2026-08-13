"""Phase 12/13 hardened — JobQueue deps, chat_id, admin ops + confirm."""
from __future__ import annotations

import tempfile
from pathlib import Path

from telegram_bot_engine.services.capability_detection.packs.loader import (
    load_all_packs, _LOADED_PACKS, _OVERLAY_KEYS, _KEYWORD_INDEX,
)
from telegram_bot_engine.services.capability_detection.ops import (
    handle_ops_command, is_ops_admin,
)
from telegram_bot_engine import generate_bot


def _reload():
    _LOADED_PACKS.clear(); _OVERLAY_KEYS.clear(); _KEYWORD_INDEX.clear()
    load_all_packs()


def test_generate_schedule_jobqueue_and_chat():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت تذكير مجدول",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_schedule"],
        )
        assert r.success
        root = Path(r.project_path)
        main = (root / "main.py").read_text(encoding="utf-8")
        gen = (root / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        env = (root / ".env.example").read_text(encoding="utf-8")
        opt = root / "requirements-optional.txt"
        assert "SCHEDULE_ENABLED" in env
        assert "list_due_reminders" in gen
        assert "chat_id" in gen
        assert "run_repeating" in main
        assert "SCHEDULE_ENABLED" in main
        assert "chat_id" in main
        if opt.is_file():
            assert "job-queue" in opt.read_text(encoding="utf-8")


def test_ops_admin_gate(monkeypatch):
    _reload()
    monkeypatch.setenv("CAPABILITY_OPS_ADMINS", "42")
    assert is_ops_admin(42) is True
    assert is_ops_admin(99) is False
    denied = handle_ops_command("/cap_health", user_id=99)
    assert denied and "مشرفين" in denied
    ok = handle_ops_command("/cap_health", user_id=42)
    assert ok and ("صحة" in ok or "فحص" in ok)


def test_ops_promote_requires_confirm(monkeypatch):
    _reload()
    monkeypatch.delenv("CAPABILITY_OPS_ADMINS", raising=False)
    monkeypatch.setenv("CAPABILITY_OPS_REQUIRE_ADMIN", "0")
    msg = handle_ops_command("/cap_promote run", user_id=1)
    assert msg and "confirm" in msg.lower() or "تأكيد" in (msg or "")
    # with confirm
    msg2 = handle_ops_command("/cap_promote run confirm", user_id=1)
    assert msg2 and "ترقية" in msg2


def test_ops_help_lists_commands(monkeypatch):
    monkeypatch.delenv("CAPABILITY_OPS_ADMINS", raising=False)
    monkeypatch.setenv("CAPABILITY_OPS_REQUIRE_ADMIN", "0")
    h = handle_ops_command("/cap_help", user_id=1)
    assert h and "cap_health" in h and "confirm" in h
    assert "cooldown" in h or "الوضع" in h


def test_generate_schedule_parser_and_batch_env():
    """Hardened parser + batch limit appear in emitted generic + env."""
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت تذكير مجدول",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_schedule"],
        )
        assert r.success
        root = Path(r.project_path)
        gen = (root / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        env = (root / ".env.example").read_text(encoding="utf-8")
        main = (root / "main.py").read_text(encoding="utf-8")
        assert "_human_duration" in gen
        assert "نصف ساعة" in gen or "بعد نصف" in gen
        assert "SCHEDULE_BATCH_LIMIT" in env
        assert "list_due_reminders(limit=" in main
        assert "mark_reminder_fired" in main


def test_generate_recurring_schedule():
    _reload()
    with tempfile.TemporaryDirectory() as d:
        r = generate_bot(
            "بوت تذكير مجدول",
            work_dir=d,
            user_id=0,
            preferred_keys=["start", "help", "scaffold_schedule"],
        )
        assert r.success
        gen = (Path(r.project_path) / "app" / "services" / "generic.py").read_text(encoding="utf-8")
        assert "_parse_recurring" in gen
        assert "recurring" in gen
        assert "interval_sec" in gen
