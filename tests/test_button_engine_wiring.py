"""Prove every UX button action is wired into catalog, signed callbacks, and engine."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ui_button_actions() -> set[str]:
    actions: set[str] = set()
    for base in ("lumen/bot/ui", "lumen/bot/handlers", "lumen/bot/routers"):
        for f in (ROOT / base).glob("*.py"):
            src = f.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(
                r'UiButton\(\s*["\'][^"\']+["\']\s*,\s*["\']([a-z_]+)["\']', src
            ):
                actions.add(m.group(1))
    return actions


def test_all_ui_buttons_in_catalog_and_signed():
    from lumen.engine.services.ui_state.catalog import is_known_action
    from lumen.bot.ui.signed_callback import encode_signed, decode_signed
    from lumen.bot.ui import signed_callback as sc

    actions = _ui_button_actions()
    assert actions, "no UiButton actions found"
    short = sc._ACTION_SHORT
    for a in sorted(actions):
        assert is_known_action(a), f"catalog missing {a}"
        assert a in short, f"_ACTION_SHORT missing {a}"
        wire = encode_signed(a, "0", user_id=1)
        assert len(wire.encode("utf-8")) <= 64
        parsed = decode_signed(wire, user_id=1)
        assert parsed is not None and parsed[0] == a


def test_callback_router_or_apply_handles_every_action():
    cr = (ROOT / "lumen/bot/ui/callback_router.py").read_text(encoding="utf-8")
    controller = (ROOT / "lumen/engine/services/ui_state/controller.py").read_text(
        encoding="utf-8"
    )
    for a in sorted(_ui_button_actions()):
        special = f'action_id == "{a}"' in cr
        apply = f'action_id == "{a}"' in controller
        assert special or apply, f"unhandled action {a}"


def test_host_panel_actions_map_to_hostservice_methods():
    from lumen.engine.services.hosting.service import HostingService

    for meth in ("status", "stop", "logs", "diagnose", "start"):
        assert hasattr(HostingService, meth)


def test_apply_action_sets_dash_effects():
    from lumen.engine.services.ui_state.controller import apply_action
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState

    for action in ("dash_status", "dash_stop", "dash_diagnose", "dash_logs"):
        r = apply_action(
            EngineUiState(phase=EngineUiPhase.HOME), action, "0", user_id=1
        )
        assert r.ok, r.message_ar
        assert r.dash_effect == action
        assert r.state.phase == EngineUiPhase.DASHBOARD


def test_execute_dash_effect_fail_closed_no_instance():
    import asyncio
    os.environ["ENVIRONMENT"] = "dev"
    from lumen.bot.ui.dash_actions import execute_dash_effect

    async def _run():
        return await execute_dash_effect(
            effect="dash_logs",
            target="0",
            user_id=999999002,
            user_data={"slots": {}},
            message=None,
        )

    note = asyncio.run(_run())
    assert note
    assert "مثيل" in note or "غير" in note or "FAIL" in note or "لا" in note



def test_token_handler_scrubs_and_attaches_panel():
    src = (ROOT / "lumen/bot/handlers/token_handler.py").read_text(encoding="utf-8")
    assert src.count("scrub_and_confirm") >= 3
    assert "attach_host_panel" in src


def test_git_router_sections_and_actionable():
    src = (ROOT / "lumen/bot/routers/git_router.py").read_text(encoding="utf-8")
    assert "store_sections" in src and "section_keyboard" in src
    assert "private_clone_error" in src or "needs_auth_prompt" in src
