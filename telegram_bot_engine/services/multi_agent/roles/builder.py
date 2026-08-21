"""Builder role — deterministic generation via existing engine path."""
from __future__ import annotations

from pathlib import Path

from ..state import AgentRole, AgentState, AgentStatus


def run_builder(state: AgentState, *, work_dir: Path) -> AgentState:
    state.set_status(AgentStatus.BUILDING, role=AgentRole.BUILDER)
    state.attempts = int(state.attempts or 0) + 1
    req = (state.spec_request or state.user_text or "").strip()
    preferred = list(state.preferred_keys or []) or None

    try:
        # Call engine generate_bot directly (same as helpers.run_generation core)
        from telegram_bot_engine import generate_bot

        result = generate_bot(
            req,
            work_dir=str(work_dir),
            user_id=int(state.user_id or 0),
            preferred_keys=preferred,
        )
    except Exception as exc:
        state.build_success = False
        state.build_errors = [f"{type(exc).__name__}:{exc}"]
        state.record(AgentRole.BUILDER, "build_exception", type(exc).__name__)
        state.set_status(AgentStatus.FAILED, role=AgentRole.BUILDER, detail=type(exc).__name__)
        return state

    success = bool(getattr(result, "success", False))
    state.build_success = success
    path = getattr(result, "project_path", None) or getattr(result, "output_dir", None) or ""
    state.generated_path = str(path or "")
    errs = list(getattr(result, "errors", None) or [])
    state.build_errors = [str(e)[:200] for e in errs[:20]]
    meta = dict(getattr(result, "metadata", None) or {})
    meta["orchestrator_state_id"] = state.state_id
    state.build_metadata = meta
    # stash raw result for caller
    state.build_metadata["_result_type"] = type(result).__name__
    state.record(
        AgentRole.BUILDER,
        "build_done",
        f"success={success} path={state.generated_path[:80]}",
    )
    if not success:
        state.set_status(AgentStatus.FAILED, role=AgentRole.BUILDER, detail="build_failed")
    # keep GenerationResult on state for return (non-serializable side channel)
    state.build_metadata["_generation_result"] = result  # type: ignore
    return state
