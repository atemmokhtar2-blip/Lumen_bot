"""
Multi-Agent Orchestrator — Phase A.

Flow: ROUTER → ARCHITECT → BUILDER → CRITIC → DELIVER
Shared blackboard: AgentState. No Telegram knowledge.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from .state import AgentRole, AgentState, AgentStatus, save_state
from .roles import run_architect, run_builder, run_critic, run_router

logger = logging.getLogger(__name__)


def orchestrator_enabled() -> bool:
    return (os.environ.get("MULTI_AGENT_ORCHESTRATOR") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def orchestrate_generate(
    request: str,
    work_dir: str | Path,
    *,
    user_id: int = 0,
    preferred_keys: Optional[list[str]] = None,
    spec_request: Optional[str] = None,
) -> Any:
    """
    Run Phase A pipeline and return the underlying GenerationResult
    (same contract as telegram_bot_engine.generate_bot).
    """
    state = AgentState(
        user_id=int(user_id or 0),
        user_text=request or "",
        spec_request=(spec_request or request or ""),
        preferred_keys=list(preferred_keys or []),
    )
    state.record(AgentRole.ORCHESTRATOR, "start", request[:120] if request else "")
    save_state(state)

    # 1) Router
    state = run_router(state)
    save_state(state)

    # Only full build pipeline for generate-like intents when entered via this API
    # (callers already decided to generate)
    if state.user_intent in {"chat_or_other"} and state.capability_id not in {
        "generate_bot", "refine_bot", "",
    }:
        # Non-generate capability — still allow build if caller forced generate entry
        state.record(AgentRole.ORCHESTRATOR, "non_generate_capability", state.capability_id)

    # 2) Architect
    state = run_architect(state)
    save_state(state)

    # 3) Builder
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    state = run_builder(state, work_dir=work)
    save_state(state)

    # 4) Critic (one shot — loop is Phase C)
    if state.build_success:
        state = run_critic(state)
    else:
        state.qa_passed = False
        state.qa_report = {"ok": False, "errors": list(state.build_errors or ["build_failed"])}
        state.set_status(AgentStatus.FAILED, role=AgentRole.CRITIC, detail="skip_qa_build_failed")
    save_state(state)

    # 5) Deliver message (text only; UI layer may use it)
    if state.status == AgentStatus.PASSED.value:
        state.final_message = (
            f"تم البناء بنجاح.\n"
            f"المسار: {state.generated_path}\n"
            f"QA: PASSED\n"
            f"state_id: {state.state_id}"
        )
        state.set_status(AgentStatus.DELIVERED, role=AgentRole.ORCHESTRATOR)
    else:
        qa_errs = (state.qa_report or {}).get("errors") or state.build_errors or []
        state.final_message = (
            f"انتهى المسار بحالة {state.status}.\n"
            f"المسار: {state.generated_path or '—'}\n"
            f"QA: {'PASSED' if state.qa_passed else 'FAILED'}\n"
            f"تفاصيل: {'; '.join(str(e) for e in qa_errs[:3])}\n"
            f"state_id: {state.state_id}"
        )
        state.record(AgentRole.ORCHESTRATOR, "deliver_failed_state", state.status)
    save_state(state)

    logger.info(
        "orchestrator done state_id=%s status=%s path=%s qa=%s",
        state.state_id,
        state.status,
        state.generated_path,
        state.qa_passed,
    )

    # Return engine GenerationResult for backward compatibility
    result = (state.build_metadata or {}).pop("_generation_result", None)
    if result is not None:
        try:
            meta = dict(getattr(result, "metadata", None) or {})
            meta["multi_agent"] = state.to_dict()
            # do not leave non-serializable
            meta.pop("_generation_result", None)
            result.metadata = meta
        except Exception:
            pass
        return result

    from telegram_bot_engine.core.result import GenerationResult
    return GenerationResult(
        success=False,
        errors=list(state.build_errors or ["orchestrator_no_result"]),
        metadata={"multi_agent": state.to_dict()},
    )
