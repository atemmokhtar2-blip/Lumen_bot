"""Human-in-the-loop — pending sensitive tool actions until explicit confirm/reject."""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .blackboard import BlackboardStore, get_blackboard
from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)


def _ttl_seconds() -> float:
    try:
        return max(60.0, min(86400.0, float(os.environ.get("MULTI_AGENT_HITL_TTL_SEC") or "1800")))
    except ValueError:
        return 1800.0


@dataclass
class PendingAction:
    action_id: str
    state_id: str
    user_id: int
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: str = "pending"  # pending | confirmed | rejected | expired

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PendingAction":
        return cls(
            action_id=str(d.get("action_id") or ""),
            state_id=str(d.get("state_id") or ""),
            user_id=int(d.get("user_id") or 0),
            tool=str(d.get("tool") or ""),
            params=dict(d.get("params") or {}),
            reason=str(d.get("reason") or ""),
            created_at=float(d.get("created_at") or time.time()),
            expires_at=float(d.get("expires_at") or 0.0),
            status=str(d.get("status") or "pending"),
        )

    def is_expired(self) -> bool:
        return time.time() > float(self.expires_at or 0.0)


def tool_requires_confirmation(tool: str) -> bool:
    try:
        from telegram_bot_engine.services.tool_runtime.registry import tool_requires_confirmation as trc
        return bool(trc(tool))
    except Exception:
        # Fail-closed for known sensitive names
        return (tool or "").strip() in {
            "create_repo", "git_push", "host_start", "host_stop", "repo_modify",
        }


def request_confirmation(
    state: AgentState,
    tool: str,
    params: dict[str, Any] | None = None,
    *,
    reason: str = "",
    board: BlackboardStore | None = None,
) -> PendingAction:
    """Park state as AWAITING_CONFIRMATION; return pending action token."""
    board = board or get_blackboard()
    action_id = uuid.uuid4().hex[:12]
    pending = PendingAction(
        action_id=action_id,
        state_id=state.state_id,
        user_id=int(state.user_id or 0),
        tool=(tool or "").strip(),
        params=dict(params or {}),
        reason=reason or f"تأكيد مطلوب قبل تنفيذ: {tool}",
        expires_at=time.time() + _ttl_seconds(),
    )
    state.extensions["pending_action"] = pending.to_dict()
    state.extensions["hitl"] = {
        "action_id": action_id,
        "tool": pending.tool,
        "requires_confirmation": True,
    }
    try:
        state.transition(
            AgentStatus.AWAITING_CONFIRMATION,
            role=AgentRole.HITL,
            detail=pending.tool,
            force=True,
        )
    except Exception:
        state.status = AgentStatus.AWAITING_CONFIRMATION.value
    state.final_message = (
        f"⚠️ إجراء حساس يحتاج تأكيدك\n"
        f"الأداة: `{pending.tool}`\n"
        f"السبب: {pending.reason}\n"
        f"معرّف التأكيد: `{action_id}`\n"
        f"أرسل: تأكيد {action_id}   أو   رفض {action_id}\n"
        f"(ينتهي خلال {int(_ttl_seconds() // 60)} دقيقة)"
    )
    state.record(AgentRole.HITL, "awaiting_confirmation", f"{pending.tool}:{action_id}")
    board.put(state)
    return pending


def _load_pending(state: AgentState) -> Optional[PendingAction]:
    raw = (state.extensions or {}).get("pending_action")
    if not isinstance(raw, dict):
        return None
    return PendingAction.from_dict(raw)


def confirm_action(
    state_id: str,
    action_id: str,
    *,
    user_id: int = 0,
    board: BlackboardStore | None = None,
) -> tuple[bool, AgentState | None, str]:
    """Mark pending action confirmed. Caller runs the tool afterward."""
    board = board or get_blackboard()
    state = board.get(state_id)
    if state is None:
        return False, None, "state_not_found"
    if user_id and int(state.user_id or 0) not in {0, int(user_id)}:
        return False, state, "user_mismatch"
    pending = _load_pending(state)
    if pending is None or pending.action_id != action_id:
        return False, state, "action_mismatch"
    if pending.status != "pending":
        return False, state, f"already_{pending.status}"
    if pending.is_expired():
        pending.status = "expired"
        state.extensions["pending_action"] = pending.to_dict()
        try:
            state.transition(AgentStatus.CANCELLED, role=AgentRole.HITL, detail="expired", force=True)
        except Exception:
            state.status = AgentStatus.CANCELLED.value
        state.final_message = f"انتهت صلاحية التأكيد `{action_id}`."
        board.put(state)
        return False, state, "expired"

    pending.status = "confirmed"
    state.extensions["pending_action"] = pending.to_dict()
    state.extensions["hitl_confirmed"] = True
    state.record(AgentRole.HITL, "confirmed", f"{pending.tool}:{action_id}")
    # Resume routing so orchestrator/tool runner can execute
    try:
        state.transition(AgentStatus.ROUTING, role=AgentRole.HITL, detail="confirmed", force=True)
    except Exception:
        state.status = AgentStatus.ROUTING.value
    board.put(state)
    return True, state, "ok"


def reject_action(
    state_id: str,
    action_id: str,
    *,
    user_id: int = 0,
    board: BlackboardStore | None = None,
) -> tuple[bool, AgentState | None, str]:
    board = board or get_blackboard()
    state = board.get(state_id)
    if state is None:
        return False, None, "state_not_found"
    if user_id and int(state.user_id or 0) not in {0, int(user_id)}:
        return False, state, "user_mismatch"
    pending = _load_pending(state)
    if pending is None or pending.action_id != action_id:
        return False, state, "action_mismatch"
    pending.status = "rejected"
    state.extensions["pending_action"] = pending.to_dict()
    state.record(AgentRole.HITL, "rejected", f"{pending.tool}:{action_id}")
    try:
        state.transition(AgentStatus.CANCELLED, role=AgentRole.HITL, detail="rejected", force=True)
    except Exception:
        state.status = AgentStatus.CANCELLED.value
    state.final_message = f"تم رفض الإجراء `{pending.tool}` (معرّف: {action_id})."
    board.put(state)
    return True, state, "ok"


def parse_confirmation_message(text: str) -> tuple[str, str] | None:
    """Parse 'تأكيد <id>' / 'confirm <id>' / 'رفض <id>' / 'reject <id>'."""
    raw = (text or "").strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) < 2:
        return None
    verb = parts[0].lower()
    action_id = parts[1].strip("`")
    if verb in {"تأكيد", "تاكيد", "confirm", "yes", "موافق"}:
        return ("confirm", action_id)
    if verb in {"رفض", "reject", "no", "الغاء", "إلغاء"}:
        return ("reject", action_id)
    return None
