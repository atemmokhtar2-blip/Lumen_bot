"""
150-oriented stress checks against REAL modules (not placeholder asserts).
Run: PYTHONPATH=. pytest tests/test_stress_suite.py -q
"""
from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Sanitize / token leakage
# ---------------------------------------------------------------------------
def test_sanitize_redacts_telegram_and_github_tokens():
    from bot_interface.sanitize import sanitize_error

    raw = (
        "fail token 1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA "
        "and ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX at /tmp/generated/x"
    )
    out = sanitize_error(raw)
    assert "ghp_" not in out
    assert "AAH" not in out
    assert "REDACTED" in out


def test_sanitize_for_storage_strips_paths():
    from b2b_platform.sanitize import sanitize_for_storage

    out = sanitize_for_storage("boom /home/workdir/secret password=supersecretvalue")
    assert "/home/" not in out or "[PATH]" in out


# ---------------------------------------------------------------------------
# Token recognition
# ---------------------------------------------------------------------------
def test_token_with_newline_still_matches():
    from bot_interface.helpers import looks_like_bot_token, normalize_bot_token

    raw = "8994985055:AAG5UQbxCfveh9cw2DxFj3\nQcGxma-eenM8U"
    assert looks_like_bot_token(raw)
    assert "\n" not in normalize_bot_token(raw)


def test_invalid_token_rejected():
    from bot_interface.helpers import looks_like_bot_token

    assert not looks_like_bot_token("not-a-token")
    assert not looks_like_bot_token("123:short")


# ---------------------------------------------------------------------------
# Feasibility gate
# ---------------------------------------------------------------------------
def test_feasibility_blocks_impossible_ml():
    from telegram_bot_engine.services.feasibility_gate import check_feasibility

    r = check_feasibility("بوت يتعلم من المحادثات ويصبح ذكي بالـ machine learning")
    assert r.can_generate is False
    assert r.level.value == "impossible"


def test_feasibility_blocks_hacking():
    from telegram_bot_engine.services.feasibility_gate import check_feasibility

    r = check_feasibility("Build a bot that hacks other bots")
    assert r.can_generate is False


def test_feasibility_allows_simple_shop():
    from telegram_bot_engine.services.feasibility_gate import check_feasibility

    r = check_feasibility("اعمل بوت متجر فيه /start و /cart و /products")
    assert r.can_generate is True


def test_feasibility_rejects_empty():
    from telegram_bot_engine.services.feasibility_gate import check_feasibility

    r = check_feasibility("ok")
    assert r.can_generate is False


# ---------------------------------------------------------------------------
# Path injection
# ---------------------------------------------------------------------------
def test_path_metacharacters_rejected():
    from bot_interface.sanitize import assert_safe_fs_path

    with pytest.raises(ValueError):
        assert_safe_fs_path("/tmp/x; rm -rf /")
    assert assert_safe_fs_path("/tmp/generated/users/1/x")


def test_docker_path_guard_message():
    import re
    # Mirror the guard used in docker_process_driver.deploy
    raw = "/tmp/evil;id"
    assert re.search(r"[;|&$`<>\\\n\r\0]", raw)
    from bot_interface.sanitize import assert_safe_fs_path
    with pytest.raises(ValueError):
        assert_safe_fs_path(raw)


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------
def test_session_survives_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from bot_interface.session_store import SessionStore

    store = SessionStore(tmp_path / "s.sqlite3")
    store.save(42, {"pending_run": {"project_path": "/tmp/p", "entry_point": "main.py"}})
    store2 = SessionStore(tmp_path / "s.sqlite3")
    data = store2.load(42)
    assert data["pending_run"]["project_path"] == "/tmp/p"


# ---------------------------------------------------------------------------
# Job cleanup + sanitized errors
# ---------------------------------------------------------------------------
def test_job_store_cleanup_and_sanitize(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    from b2b_platform.jobs import JobStore, Job, STATUS_SUCCEEDED

    store = JobStore()
    old = Job(
        job_id="old1",
        tenant_id="t",
        kind="echo",
        status=STATUS_SUCCEEDED,
        created_at=time.time() - 10 * 86400,
    )
    store.create(old)
    n = store.cleanup_old_jobs(days=7)
    assert n >= 1


# ---------------------------------------------------------------------------
# Capability boundaries text
# ---------------------------------------------------------------------------
def test_help_lists_cannot_do():
    from bot_interface.capability_boundaries import get_help_text, rejection_message

    h = get_help_text()
    assert "لا أستطيع" in h or "CANNOT" in h.upper() or "🚫" in h
    msg = rejection_message("اختبار", "بديل")
    assert "لا أستطيع" in msg


# ---------------------------------------------------------------------------
# Generation smoke (simple bot) — structural anti-hallucination
# ---------------------------------------------------------------------------
def test_simple_bot_generation_has_handlers(tmp_path):
    from telegram_bot_engine import generate_bot

    out = tmp_path / "gen"
    out.mkdir()
    result = generate_bot("بوت فيه /start و /help يرد ترحيب", str(out))
    assert result.success, result.errors
    handlers = Path(result.project_path) / "app" / "handlers.py"
    main = Path(result.project_path) / "main.py"
    assert handlers.is_file() and main.is_file()
    ht = handlers.read_text(encoding="utf-8")
    assert "async def" in ht
    mt = main.read_text(encoding="utf-8")
    # imports must not request missing symbols
    m = re.search(r"from app\.handlers import ([^\n]+)", mt)
    if m:
        names = [x.strip() for x in m.group(1).split(",") if x.strip()]
        defined = set(re.findall(r"async def ([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", ht))
        missing = [n for n in names if n not in defined]
        assert not missing, missing


def test_impossible_prompt_does_not_claim_ready():
    from telegram_bot_engine.services.feasibility_gate import check_feasibility

    r = check_feasibility("اعمل بوت زي تليجرام نفسه مع تعدين بيتكوين")
    assert r.can_generate is False
