"""Builder agent — deterministic generate_bot only."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..protocol import Agent
from ..state import AgentRole, AgentState, AgentStatus


class BuilderAgent(Agent):
    role = AgentRole.BUILDER.value
    name = "builder"
    order = 30

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        state.transition(AgentStatus.BUILDING, role=AgentRole.BUILDER)
        state.attempts = int(state.attempts or 0) + 1
        ctx = context or {}
        work_dir = Path(ctx.get("work_dir") or state.extensions.get("work_dir") or ".")
        work_dir.mkdir(parents=True, exist_ok=True)

        req = (state.spec_request or state.user_text or "").strip()
        preferred = list(state.preferred_keys or []) or None

        try:
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
            state.transition(AgentStatus.FAILED, role=AgentRole.BUILDER, detail=type(exc).__name__)
            return state

        success = bool(getattr(result, "success", False))
        state.build_success = success
        path = getattr(result, "project_path", None) or getattr(result, "output_dir", None) or ""
        state.generated_path = str(path or "")
        errs = list(getattr(result, "errors", None) or [])
        state.build_errors = [str(e)[:200] for e in errs[:20]]
        meta = dict(getattr(result, "metadata", None) or {})
        # strip non-serializable
        meta = {k: v for k, v in meta.items() if not str(k).startswith("_")}
        meta["orchestrator_state_id"] = state.state_id
        state.build_metadata = meta
        # Side channel for orchestrator return only (never persisted in to_dict)
        state.extensions["_generation_result"] = result
        state.record(AgentRole.BUILDER, "build_done", f"success={success}")
        if not success:
            state.transition(AgentStatus.FAILED, role=AgentRole.BUILDER, detail="build_failed")
        return state


def run_builder(state: AgentState, *, work_dir: Path) -> AgentState:
    return BuilderAgent().run(state, context={"work_dir": work_dir})
