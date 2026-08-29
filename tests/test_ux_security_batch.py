"""UX + security batch: prove real wiring, not phantom modules."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest


def test_rtl_code_path_isolates_ltr():
    from lumen.bot.ui.rtl_text import code_path, isolate_ltr
    p = code_path("/tmp/user/project")
    assert "`" in p
    assert "\u2066" in p or "\u2066" in repr(p) or "\u2066" in p
    assert "\u2066" in code_path("x") or "\u2066" in isolate_ltr("x")


def test_repo_sections_from_simple_contract():
    from lumen.bot.ui.repo_sections import (
        build_sections_from_contract, get_section, store_sections,
    )
    contract = SimpleNamespace(
        to_user_summary=lambda: "ملخص تجريبي للبوت",
        entry_points=[SimpleNamespace(path="main.py"), SimpleNamespace(path="bot.py")],
        dependencies=["python-telegram-bot==21.0"],
        frameworks=["python-telegram-bot"],
        architecture_style="telegram_bot",
        is_telegram_bot=True,
    )
    sections = build_sections_from_contract(contract, path="/tmp/x", url="https://github.com/o/r")
    assert "header" in sections and "summary" in sections
    ud: dict = {}
    store_sections(ud, sections)
    assert "ملخص" in get_section(ud, "summary")


def test_actionable_private_clone_has_button():
    from lumen.bot.ui.actionable_errors import private_clone_error
    text, markup = private_clone_error(url="https://github.com/o/private", user_id=42)
    assert "خاص" in text or "مصادقة" in text
    rows = getattr(markup, "inline_keyboard", None)
    assert rows and len(rows) >= 1
    data = getattr(rows[0][0], "callback_data", "") or ""
    assert data.startswith("L2.")


def test_host_panel_includes_logs_and_stop():
    from lumen.bot.ui.host_panel import host_panel_buttons, format_host_success
    rows = host_panel_buttons(instance_index="0")
    labels = [b.text for row in rows for b in row]
    actions = [b.action for row in rows for b in row]
    assert any("الحالة" in t for t in labels)
    assert any("السجلات" in t for t in labels)
    assert any("إيقاف" in t for t in labels)
    assert "dash_logs" in actions
    assert "dash_stop" in actions
    assert "host_restart" in actions


def test_signed_callback_new_actions_roundtrip():
    from lumen.bot.ui.signed_callback import encode_signed, decode_signed
    uid = 12345
    for action, arg in (
        ("host_restart", "0"),
        ("ask_gh_token", "clone"),
        ("ask_bot_token", "host"),
        ("repo_sec", "summary"),
        ("dash_logs", "0"),
    ):
        wire = encode_signed(action, arg, user_id=uid)
        assert len(wire.encode("utf-8")) <= 64, (action, wire, len(wire))
        parsed = decode_signed(wire, user_id=uid)
        assert parsed is not None, action
        act, a = parsed
        assert act == action
        assert a == arg


def test_catalog_knows_new_actions():
    from lumen.engine.services.ui_state.catalog import is_known_action, get_action
    for a in ("host_restart", "ask_gh_token", "ask_bot_token", "repo_sec", "dash_logs"):
        assert is_known_action(a), a
    # dash_logs allowed outside pure DASHBOARD (host panel safety)
    spec = get_action("dash_logs")
    assert spec is not None
    from lumen.engine.services.ui_state.models import EngineUiPhase
    assert EngineUiPhase.HOME in spec.allowed_phases
    assert EngineUiPhase.DASHBOARD in spec.allowed_phases


def test_apply_action_dash_logs_sets_effect():
    from lumen.engine.services.ui_state.controller import apply_action
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
    st = EngineUiState(phase=EngineUiPhase.HOME)
    result = apply_action(st, "dash_logs", "0", user_id=1)
    assert result.ok, result.message_ar
    assert result.dash_effect == "dash_logs"
    assert result.dash_target == "0"
    assert result.state.phase == EngineUiPhase.DASHBOARD


def test_hosting_service_logs_method_exists():
    import inspect
    from lumen.engine.services.hosting.service import HostingService
    assert hasattr(HostingService, "logs")
    sig = inspect.signature(HostingService.logs)
    assert "instance_id" in sig.parameters
    assert "user_id" in sig.parameters


def test_dash_actions_handles_logs_effect():
    src = Path("lumen/bot/ui/dash_actions.py").read_text()
    assert 'effect == "dash_logs"' in src or "dash_logs" in src
    assert "svc.logs" in src


def test_token_handler_calls_scrub_and_host_panel():
    src = Path("lumen/bot/handlers/token_handler.py").read_text()
    assert "scrub_and_confirm" in src
    assert "attach_host_panel" in src
    assert "token_hygiene" in src
    assert "host_panel" in src


def test_git_router_uses_sections_and_actionable():
    src = Path("lumen/bot/routers/git_router.py").read_text()
    assert "section_keyboard" in src
    assert "private_clone_error" in src
    assert "store_sections" in src


def test_callback_router_handles_direct_actions():
    src = Path("lumen/bot/ui/callback_router.py").read_text()
    assert 'action_id == "repo_sec"' in src
    assert 'action_id == "ask_gh_token"' in src
    assert 'action_id == "ask_bot_token"' in src
    assert 'action_id == "host_restart"' in src


def test_secret_prompt_webapp_optional():
    from lumen.bot.ui.secret_prompt import secrets_web_url, build_secret_prompt_markup
    import os
    # Without PUBLIC_BASE_URL → None (fail closed, chat path remains)
    os.environ.pop("PUBLIC_BASE_URL", None)
    os.environ.pop("WEB_APP_URL", None)
    assert secrets_web_url(kind="bot") is None
    assert build_secret_prompt_markup(kind="bot", user_id=1) is None
    os.environ["PUBLIC_BASE_URL"] = "https://app.example.com"
    assert secrets_web_url(kind="bot") == "https://app.example.com/secrets?kind=bot"
    markup = build_secret_prompt_markup(kind="bot", user_id=1)
    assert markup is not None
    btn = markup.inline_keyboard[0][0]
    assert getattr(btn, "web_app", None) is not None
    os.environ.pop("PUBLIC_BASE_URL", None)
