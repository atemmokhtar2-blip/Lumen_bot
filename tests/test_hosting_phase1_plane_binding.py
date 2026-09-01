"""Phase 1 — generation delivery must not silent-bind trial; post_host ≠ LiveRunner."""
from __future__ import annotations

import asyncio
from pathlib import Path

from lumen.engine.services.runtime_planes import RuntimePlane

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_delivery_does_not_auto_set_pending_live_run() -> None:
    src = (REPO_ROOT / "lumen/bot/generation_steps/delivery.py").read_text(encoding="utf-8")
    assert 'context.user_data["pending_live_run"]' not in src
    assert 'context.user_data["pending_run"]' not in src
    assert 'context.user_data["pending_deploy"]' not in src
    assert "pending_live_run" in src  # cleared via pop


def test_post_actions_host_clears_trial_keys() -> None:
    src = (REPO_ROOT / "lumen/bot/ui/post_actions.py").read_text(encoding="utf-8")
    host_at = src.find('if effect == "post_host"')
    trial_at = src.find('if effect == "post_trial"')
    assert host_at > 0 and trial_at > 0
    host_body = src[host_at : host_at + 1200]
    trial_body = src[trial_at : trial_at + 1200]
    assert 'ud.pop("pending_live_run"' in host_body
    assert 'ud.pop("pending_run"' in host_body
    assert 'ud["pending_host"]' in host_body
    assert 'ud.pop("pending_host"' in trial_body
    assert "RuntimePlane.PERMANENT_HOST" in host_body
    assert "RuntimePlane.TRIAL_CHAT" in trial_body


def test_runtime_plane_enum_values() -> None:
    assert RuntimePlane.PERMANENT_HOST.value == "permanent_host"
    assert RuntimePlane.TRIAL_CHAT.value == "trial_chat"


def test_token_handler_checks_pending_host_before_live() -> None:
    src = (REPO_ROOT / "lumen/bot/handlers/token_handler.py").read_text(encoding="utf-8")
    host_pos = src.find("pending_host")
    live_pos = src.find("pending_live_run")
    assert host_pos > 0
    assert live_pos > 0
    assert host_pos < live_pos


def test_hosting_router_binds_host_service() -> None:
    src = (REPO_ROOT / "lumen/bot/routers/hosting_router.py").read_text(encoding="utf-8")
    assert "get_hosting_service" in src
    assert "LiveRunner" in src or "not trial" in src.lower()


def test_execute_post_host_sets_plane(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    from lumen.bot.ui import post_actions

    class _U:
        id = 42

    class _C:
        user_data: dict = {}

    ctx = _C()
    ctx.user_data = {
        "pending_live_run": {"plane": "trial_chat"},
        "pending_run": {"plane": "trial_chat"},
    }

    note = asyncio.run(
        post_actions.execute_post_side_effect(
            effect="post_host",
            project_ref=str(tmp_path),
            message=None,
            context=ctx,
            user=_U(),
        )
    )
    assert "pending_host" in ctx.user_data
    assert ctx.user_data["pending_host"]["plane"] == RuntimePlane.PERMANENT_HOST.value
    assert "pending_live_run" not in ctx.user_data
    assert "pending_run" not in ctx.user_data
    assert "HostService" in note or "permanent" in note.lower() or "دائمة" in note


def test_execute_post_trial_clears_host(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    from lumen.bot.ui import post_actions

    class _U:
        id = 7

    class _C:
        user_data: dict = {}

    ctx = _C()
    ctx.user_data = {"pending_host": {"project_path": "/old"}}

    note = asyncio.run(
        post_actions.execute_post_side_effect(
            effect="post_trial",
            project_ref=str(tmp_path),
            message=None,
            context=ctx,
            user=_U(),
        )
    )
    assert "pending_host" not in ctx.user_data
    assert ctx.user_data.get("pending_live_run", {}).get("plane") == RuntimePlane.TRIAL_CHAT.value
    assert "LiveRunner" in note or "trial" in note.lower() or "تجربة" in note
