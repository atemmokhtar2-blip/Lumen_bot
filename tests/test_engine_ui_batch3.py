"""Batch 3 — post-generation trial vs permanent host UI."""
from __future__ import annotations

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    RuntimePlaneHint,
    apply_action,
    buttons_for_state,
)


def test_gen_done_buttons_include_trial_and_host():
    st = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/tmp/proj")
    actions = [b.action for row in buttons_for_state(st) for b in row]
    assert "post_trial" in actions
    assert "post_host" in actions
    assert "post_zip" in actions
    assert "post_preview" in actions


def test_post_trial_sets_plane():
    st = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/tmp/proj")
    r = apply_action(st, "post_trial")
    assert r.ok
    assert r.post_side_effect == "post_trial"
    assert r.state.plane == RuntimePlaneHint.TRIAL_CHAT


def test_post_host_sets_plane():
    st = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/tmp/proj")
    r = apply_action(st, "post_host")
    assert r.ok
    assert r.post_side_effect == "post_host"
    assert r.state.plane == RuntimePlaneHint.PERMANENT_HOST


def test_post_without_project_fails_soft():
    st = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="")
    r = apply_action(st, "post_trial")
    assert r.post_side_effect == ""
    assert "مشروع" in r.message_ar


def test_execute_post_trial_sets_pending(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from lumen.bot.ui.post_actions import execute_post_side_effect

    proj = tmp_path / "bot"
    proj.mkdir()
    (proj / "main.py").write_text("print(1)\n")
    ctx = SimpleNamespace(user_data={})
    user = SimpleNamespace(id=42)
    msg = SimpleNamespace(reply_text=None, reply_document=None)

    async def _run():
        return await execute_post_side_effect(
            effect="post_trial",
            project_ref=str(proj),
            message=msg,
            context=ctx,
            user=user,
        )

    note = asyncio.get_event_loop().run_until_complete(_run())
    assert "تجربة" in note or "توكن" in note
    assert ctx.user_data.get("pending_run", {}).get("project_path") == str(proj)
    assert ctx.user_data.get("pending_run", {}).get("plane") == "trial_chat"


def test_execute_post_host_sets_pending_host(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from lumen.bot.ui.post_actions import execute_post_side_effect

    proj = tmp_path / "bot"
    proj.mkdir()
    ctx = SimpleNamespace(user_data={"pending_run": {"x": 1}})
    user = SimpleNamespace(id=7)
    msg = SimpleNamespace()

    async def _run():
        return await execute_post_side_effect(
            effect="post_host",
            project_ref=str(proj),
            message=msg,
            context=ctx,
            user=user,
        )

    note = asyncio.get_event_loop().run_until_complete(_run())
    assert "دائمة" in note or "Firecracker" in note or "توكن" in note
    assert ctx.user_data.get("pending_host", {}).get("project_path") == str(proj)
    assert "pending_run" not in ctx.user_data  # cleared for host routing
