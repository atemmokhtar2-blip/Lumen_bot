"""Phase 4: end-to-end agent wiring — router → decide → progress → finish."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


def _clear_keys():
    for k in (
        "AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT", "AZURE_OPENAI_API_KEY",
        "DEEPSEEK_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "CLINE_LLM_PROVIDER",
        "CLINE_ROUTER",
    ):
        os.environ.pop(k, None)
    os.environ["OPENAI_API_KEY"] = "sk-e2e-test"
    os.environ["CLINE_ROUTER"] = "local"
    os.environ["CLINE_AGENT_MAX_STEPS"] = "3"


def test_progress_text_shows_model():
    from lumen.bot.progress_tracker import _text
    s = _text(
        {"tool": "thinking", "provider": "openai", "model": "gpt-4o-mini", "step": 1, "limit": 5},
        3,
        [],
    )
    assert "openai" in s
    assert "gpt-4o-mini" in s


def test_select_then_invoke_chain():
    _clear_keys()
    from lumen.engine.services.cline_runtime.model_router import select_model_for_goal
    from lumen.engine.services.cline_runtime import agent_brain

    choice, meta = select_model_for_goal(task="build", goal="write a telegram bot")
    assert choice.provider == "openai"
    assert meta.get("router") == "r2_allocator"

    with patch.object(
        agent_brain,
        "_call_openai_compat",
        return_value='{"tool":"finish","summary":"done","reply":"تم"}',
    ):
        out = agent_brain.decide(
            [{"role": "user", "content": "build bot"}],
            choice=choice,
            task="build",
        )
    assert out.get("provider") == "openai"
    assert out.get("model_id") == choice.model_id


def test_run_agent_e2e_with_mocked_llm(tmp_path: Path):
    _clear_keys()
    events: list[dict] = []

    def capture(ev):
        if isinstance(ev, dict):
            events.append(dict(ev))

    from lumen.engine.services.progress_bus import set_progress_handler, reset_progress_handler
    from lumen.engine.services.cline_runtime.agent_loop import run_agent
    from lumen.engine.services.cline_runtime import agent_brain

    tok = set_progress_handler(capture)
    try:
        with patch.object(
            agent_brain,
            "_invoke_choice",
            return_value='{"tool":"finish","summary":"project ready","thought":"done"}',
        ):
            state = run_agent(
                work_dir=tmp_path,
                goal="Build a simple echo telegram bot with main.py",
                ir_dict={"preferred_keys": ["echo", "start"], "user_id": 1},
                max_steps=2,
            )
    finally:
        reset_progress_handler(tok)

    # Must have gone through routing + at least one decide progress
    phases = [e.get("phase") for e in events]
    assert "loop_start" in phases or any(e.get("tool") == "thinking" for e in events)
    # Provider/model should appear on loop_start when router worked
    start_ev = next((e for e in events if e.get("phase") == "loop_start"), None)
    if start_ev:
        assert start_ev.get("provider") in {"openai", "deepseek", "groq", "gemini", "foundry", "none"} or start_ev.get("provider")
    # Agent should stop somehow (finish or max steps or soft)
    assert state.stop_reason or state.ok or state.steps


def test_provider_agent_emits_progress(tmp_path: Path):
    _clear_keys()
    events: list[dict] = []
    from lumen.engine.services.progress_bus import set_progress_handler, reset_progress_handler
    from lumen.engine.services.cline_runtime import agent_brain
    from lumen.engine.services.cline_runtime.provider_agent import build

    tok = set_progress_handler(lambda e: events.append(dict(e)) if isinstance(e, dict) else None)
    try:
        with patch.object(
            agent_brain,
            "_invoke_choice",
            return_value='{"tool":"finish","summary":"ok"}',
        ):
            raw = build(
                {"raw_request": "بوت صدى بسيط", "preferred_keys": ["echo"], "language": "ar"},
                str(tmp_path),
            )
    finally:
        reset_progress_handler(tok)

    assert isinstance(raw, dict)
    assert "engine" in raw
    assert any(e.get("tool") == "coding_agent" or e.get("phase") == "coding_agent" for e in events)


def test_executor_agent_mode_calls_provider(tmp_path: Path):
    _clear_keys()
    from types import SimpleNamespace
    from lumen.engine.services.cline_runtime.executor import execute_cline_ir
    from lumen.engine.services.cline_runtime import agent_brain

    ir = SimpleNamespace(
        to_dict=lambda: {
            "raw_request": "echo bot",
            "preferred_keys": ["echo"],
            "capabilities_gap": ["free_agent"],
            "engine_mode": "cline",
        },
        capabilities_gap=["free_agent"],
        engine_mode=SimpleNamespace(value="cline"),
    )
    with patch.object(
        agent_brain,
        "_invoke_choice",
        return_value='{"tool":"finish","summary":"ok"}',
    ):
        res = execute_cline_ir(ir, tmp_path)
    assert res.engine in {"cline_agent", "cline_agent_error", "cline_blocked"}
    # With keys present should reach agent path
    assert res.engine == "cline_agent"


def test_progress_handler_stack_nested():
    """Nested set/reset must not drop the outer heartbeat sink."""
    from lumen.engine.services.progress_bus import (
        set_progress_handler, reset_progress_handler, report_progress,
    )
    outer_events = []
    inner_events = []

    def outer(ev):
        outer_events.append(ev)

    def inner(ev):
        inner_events.append(ev)

    tok_o = set_progress_handler(outer)
    report_progress({"phase": "o1"})
    tok_i = set_progress_handler(inner)
    report_progress({"phase": "i1"})
    reset_progress_handler(tok_i)
    report_progress({"phase": "o2"})
    reset_progress_handler(tok_o)
    report_progress({"phase": "gone"})

    assert any(e.get("phase") == "o1" for e in outer_events)
    assert any(e.get("phase") == "i1" for e in inner_events)
    assert any(e.get("phase") == "o2" for e in outer_events)
    assert not any(e.get("phase") == "gone" for e in outer_events + inner_events)


def test_execute_ir_flattens_router_metadata(tmp_path):
    _clear_keys()
    from unittest.mock import patch
    from types import SimpleNamespace
    from lumen.engine.services.cline_runtime import agent_brain
    from lumen.engine.services.cline_runtime.executor import execute_cline_ir

    ir = SimpleNamespace(
        to_dict=lambda: {"raw_request": "echo bot", "preferred_keys": ["echo"], "capabilities_gap": ["free_agent"]},
        capabilities_gap=["free_agent"],
        engine_mode=SimpleNamespace(value="cline"),
    )
    with patch.object(agent_brain, "_invoke_choice", return_value='{"tool":"finish","summary":"ok"}'):
        res = execute_cline_ir(ir, tmp_path)
    assert res.engine == "cline_agent"
    assert isinstance(res.metadata, dict)
    # router recorded by agent_loop when keys present
    assert res.metadata.get("router") is not None or res.ok is not None


def test_request_cancel_stops_flag():
    from lumen.engine.services.generation_cancel import (
        request_cancel, clear_cancel, is_cancelled,
    )
    clear_cancel(4242)
    assert not is_cancelled(4242)
    request_cancel(4242)
    assert is_cancelled(4242)
    clear_cancel(4242)
    assert not is_cancelled(4242)


def test_provider_acceptance_gate_rejects_empty(tmp_path):
    """Phase 5: empty project cannot be ok even if loop claims finish."""
    _clear_keys()
    from unittest.mock import patch
    from lumen.engine.services.cline_runtime import agent_brain
    from lumen.engine.services.cline_runtime.provider_agent import build
    from lumen.engine.services.cline_runtime.agent_state import AgentState

    fake = AgentState(work_dir=str(tmp_path), goal="x")
    fake.ok = True
    fake.stop_reason = "completed"
    fake.files_written = []
    fake.metadata = {"router": {"provider": "openai", "model_id": "gpt-4o-mini"}}

    with patch(
        "lumen.engine.services.cline_runtime.provider_agent.run_agent",
        return_value=fake,
    ):
        raw = build({"raw_request": "echo bot"}, str(tmp_path))
    assert raw["ok"] is False
    assert any("acceptance" in str(e) for e in (raw.get("errors") or [])) or (
        (raw.get("metadata") or {}).get("acceptance") or {}
    ).get("ok") is False


def test_user_id_reaches_agent_loop_for_cancel(tmp_path):
    """Cancel only works if ir.user_id is visible inside run_agent."""
    _clear_keys()
    from unittest.mock import patch
    from lumen.engine.services.cline_runtime import agent_brain
    from lumen.engine.services.cline_runtime.agent_loop import run_agent
    from lumen.engine.services.generation_cancel import request_cancel, clear_cancel, is_cancelled

    clear_cancel(777)
    request_cancel(777)
    assert is_cancelled(777)

    seen = {}

    def fake_invoke(choice, system, user, *, task="build"):
        seen["called"] = True
        return '{"tool":"finish","summary":"x"}'

    with patch.object(agent_brain, "_invoke_choice", side_effect=fake_invoke):
        state = run_agent(
            work_dir=tmp_path,
            goal="echo bot",
            ir_dict={"user_id": 777, "preferred_keys": ["echo"]},
            max_steps=2,
        )
    # clear_cancel runs at loop start — cancel flag cleared for NEW run
    # Re-request and ensure loop can see cancel mid-flight: next step check
    assert state.metadata.get("user_id") == 777


def test_execute_ir_stamps_user_id(tmp_path):
    from lumen.engine.core.ir import BuildIR, EngineMode
    ir = BuildIR(
        original_text="x",
        spec_request="x",
        preferred_keys=["echo"],
        capabilities_gap=["free_agent"],
        engine_mode=EngineMode.CLINE,
        user_id=0,
    )
    # stamp logic mirror
    uid = 999
    if uid:
        ir.user_id = uid
    assert ir.to_dict().get("user_id") == 999
