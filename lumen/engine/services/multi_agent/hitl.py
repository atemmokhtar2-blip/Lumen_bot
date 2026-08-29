"""Hardened Human-in-the-loop gate — one-time tokens, audit, secret redaction."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .blackboard import BlackboardStore, get_blackboard
from .state import AgentRole, AgentState, AgentStatus

logger = logging.getLogger(__name__)

# Process-local consumed tokens (one-time use)
_CONSUMED: set[str] = set()
_CONSUMED_LOCK = threading.Lock()
_AUDIT: list[dict[str, Any]] = []
_AUDIT_LOCK = threading.Lock()


def _ttl_seconds() -> float:
    try:
        return max(60.0, min(86400.0, float(os.environ.get("MULTI_AGENT_HITL_TTL_SEC") or "900")))
    except ValueError:
        return 900.0


def _hmac_secret() -> bytes:
    raw = (os.environ.get("MULTI_AGENT_HITL_SECRET") or os.environ.get("SECRET_KEY") or "multi-agent-hitl").encode()
    return hashlib.sha256(raw).digest()


def _sign(action_id: str, state_id: str, tool: str, user_id: int, expires_at: float) -> str:
    msg = f"{action_id}|{state_id}|{tool}|{user_id}|{int(expires_at)}".encode()
    return hmac.new(_hmac_secret(), msg, hashlib.sha256).hexdigest()[:24]


def _audit(event: str, **fields: Any) -> None:
    row = {"event": event, "at": time.time(), **fields}
    with _AUDIT_LOCK:
        _AUDIT.append(row)
        if len(_AUDIT) > 500:
            del _AUDIT[:250]
    logger.info("HITL %s %s", event, {k: v for k, v in fields.items() if k != "params"})


def audit_log(*, limit: int = 50) -> list[dict[str, Any]]:
    with _AUDIT_LOCK:
        return list(_AUDIT[-max(1, min(limit, 200)):])


@dataclass
class PendingAction:
    action_id: str
    state_id: str
    user_id: int
    tool: str
    params: dict[str, Any] = field(default_factory=dict)  # redacted only
    params_digest: str = ""  # hash of real params for integrity
    reason: str = ""
    risk: str = "high"
    confirm_token: str = ""  # HMAC one-time
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: str = "pending"  # pending | confirmed | rejected | expired | consumed
    nonce: str = ""

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
            params_digest=str(d.get("params_digest") or ""),
            reason=str(d.get("reason") or ""),
            risk=str(d.get("risk") or "high"),
            confirm_token=str(d.get("confirm_token") or ""),
            created_at=float(d.get("created_at") or time.time()),
            expires_at=float(d.get("expires_at") or 0.0),
            status=str(d.get("status") or "pending"),
            nonce=str(d.get("nonce") or ""),
        )

    def is_expired(self) -> bool:
        return time.time() > float(self.expires_at or 0.0)


def _params_digest(params: dict[str, Any] | None) -> str:
    raw = repr(sorted((str(k), str(v)[:80]) for k, v in dict(params or {}).items())).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def tool_requires_confirmation(tool: str) -> bool:
    try:
        from lumen.engine.services.tool_runtime.registry import tool_requires_confirmation as trc
        return bool(trc(tool))
    except Exception:
        return (tool or "").strip() in {
            "create_repo", "git_push", "host_start", "host_stop", "repo_modify",
        }


def tool_risk(tool: str) -> str:
    t = (tool or "").strip().lower()
    if t in {"langgraph_plan_approve", "approve_plan"}:
        return "medium"
    return _tool_risk_impl(tool)


def _tool_risk_impl(tool: str) -> str:
    try:
        from lumen.engine.services.tool_runtime.registry import tool_risk_level
        return tool_risk_level(tool)
    except Exception:
        return "high" if tool_requires_confirmation(tool) else "medium"


def request_confirmation(
    state: AgentState,
    tool: str,
    params: dict[str, Any] | None = None,
    *,
    reason: str = "",
    board: BlackboardStore | None = None,
    raw_params: dict[str, Any] | None = None,
) -> PendingAction:
    """Park state AWAITING_CONFIRMATION. Secrets never stored in pending params."""
    board = board or get_blackboard()
    try:
        from lumen.engine.services.tool_runtime.registry import redact_secrets
    except Exception:
        def redact_secrets(p):  # type: ignore
            return {k: ("***REDACTED***" if "token" in str(k).lower() and v else v) for k, v in dict(p or {}).items()}

    real = dict(raw_params if raw_params is not None else (params or {}))
    action_id = secrets.token_hex(6)
    nonce = secrets.token_hex(4)
    expires = time.time() + _ttl_seconds()
    token = _sign(action_id, state.state_id, tool, int(state.user_id or 0), expires)
    risk = tool_risk(tool)

    pending = PendingAction(
        action_id=action_id,
        state_id=state.state_id,
        user_id=int(state.user_id or 0),
        tool=(tool or "").strip(),
        params=redact_secrets(real),
        params_digest=_params_digest(real),
        reason=reason or f"تأكيد مطلوب — مخاطر {risk}: {tool}",
        risk=risk,
        confirm_token=token,
        expires_at=expires,
        nonce=nonce,
    )
    # Store redacted pending + sealed real params only in memory extension key that is not serialized long-term if possible
    state.extensions["pending_action"] = pending.to_dict()
    # Sealed params for resume (still in process; board may persist — redact tokens)
    sealed = redact_secrets(real)
    # Keep non-secret params for execution; secrets must be re-supplied on confirm if critical
    state.extensions["pending_params_sealed"] = sealed
    state.extensions["hitl"] = {
        "action_id": action_id,
        "tool": pending.tool,
        "risk": risk,
        "requires_confirmation": True,
        "token_prefix": token[:6],
    }
    try:
        state.transition(
            AgentStatus.AWAITING_CONFIRMATION,
            role=AgentRole.HITL,
            detail=f"{pending.tool}:{risk}",
            force=True,
        )
    except Exception:
        state.status = AgentStatus.AWAITING_CONFIRMATION.value

    state.final_message = (
        f"⚠️ إجراء حساس — بوابة تأكيد\n"
        f"الأداة: `{pending.tool}`\n"
        f"المستوى: **{risk}**\n"
        f"السبب: {pending.reason}\n"
        f"المعرّف: `{action_id}`\n"
        f"رمز التحقق: `{token}`\n"
        f"للتأكيد أرسل:\n`تأكيد {action_id} {token}`\n"
        f"للرفض:\n`رفض {action_id}`\n"
        f"الصلاحية: {int(_ttl_seconds() // 60)} دقيقة"
    )
    state.record(AgentRole.HITL, "awaiting_confirmation", f"{pending.tool}:{action_id}:risk={risk}")
    _audit("request", action_id=action_id, tool=tool, user_id=state.user_id, risk=risk, state_id=state.state_id)
    board.put(state)
    return pending


def _load_pending(state: AgentState) -> Optional[PendingAction]:
    raw = (state.extensions or {}).get("pending_action")
    if not isinstance(raw, dict):
        return None
    return PendingAction.from_dict(raw)


def _consume_token(action_id: str, token: str) -> bool:
    key = f"{action_id}:{token}"
    with _CONSUMED_LOCK:
        if key in _CONSUMED:
            return False
        _CONSUMED.add(key)
        if len(_CONSUMED) > 2000:
            # drop arbitrary half
            for _ in range(1000):
                _CONSUMED.pop()
        return True


def confirm_action(
    state_id: str,
    action_id: str,
    *,
    user_id: int = 0,
    confirm_token: str = "",
    board: BlackboardStore | None = None,
) -> tuple[bool, AgentState | None, str]:
    """
    Confirm with action_id + HMAC token (one-time).
    Fail-closed on mismatch / expiry / reuse / user mismatch.
    """
    board = board or get_blackboard()
    state = board.get(state_id)
    if state is None:
        _audit("confirm_fail", reason="state_not_found", action_id=action_id)
        return False, None, "state_not_found"
    if user_id and int(state.user_id or 0) not in {0, int(user_id)}:
        _audit("confirm_fail", reason="user_mismatch", action_id=action_id, user_id=user_id)
        return False, state, "user_mismatch"

    pending = _load_pending(state)
    if pending is None or pending.action_id != action_id:
        _audit("confirm_fail", reason="action_mismatch", action_id=action_id)
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
        _audit("expired", action_id=action_id)
        return False, state, "expired"

    # Token required for high/critical
    expected = pending.confirm_token or _sign(
        pending.action_id, pending.state_id, pending.tool, pending.user_id, pending.expires_at
    )
    if not confirm_token or not hmac.compare_digest(str(confirm_token), str(expected)):
        _audit("confirm_fail", reason="bad_token", action_id=action_id)
        state.record(AgentRole.HITL, "bad_token", action_id)
        board.put(state)
        return False, state, "bad_token"

    if not _consume_token(action_id, confirm_token):
        _audit("confirm_fail", reason="token_reused", action_id=action_id)
        return False, state, "token_reused"

    pending.status = "confirmed"
    state.extensions["pending_action"] = pending.to_dict()
    state.extensions["hitl_confirmed"] = True
    state.extensions["hitl_execute_grant"] = {
        "action_id": action_id,
        "tool": pending.tool,
        "granted_at": time.time(),
        "single_use": True,
    }
    state.record(AgentRole.HITL, "confirmed", f"{pending.tool}:{action_id}")
    try:
        state.transition(AgentStatus.ROUTING, role=AgentRole.HITL, detail="confirmed", force=True)
    except Exception:
        state.status = AgentStatus.ROUTING.value
    board.put(state)
    _audit("confirmed", action_id=action_id, tool=pending.tool, user_id=user_id)
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
    # Verb-only reject: action_id may be empty — accept the sole pending action
    if pending is not None and not (action_id or "").strip():
        action_id = pending.action_id
    if pending is None or pending.action_id != action_id:
        return False, state, "action_mismatch"
    pending.status = "rejected"
    state.extensions["pending_action"] = pending.to_dict()
    state.extensions.pop("hitl_execute_grant", None)
    state.extensions.pop("hitl_confirmed", None)
    state.record(AgentRole.HITL, "rejected", f"{pending.tool}:{action_id}")
    try:
        state.transition(AgentStatus.CANCELLED, role=AgentRole.HITL, detail="rejected", force=True)
    except Exception:
        state.status = AgentStatus.CANCELLED.value
    state.final_message = f"تم رفض الإجراء `{pending.tool}` (معرّف: {action_id})."
    board.put(state)
    _audit("rejected", action_id=action_id, tool=pending.tool)
    return True, state, "ok"


def parse_confirmation_message(text: str) -> tuple[str, str, str] | None:
    """
    Parse:
      تأكيد <action_id> <token>
      تأكيد            (verb-only → action_id/token resolved from user_data pending)
      confirm <action_id> <token>
      confirm
      رفض <action_id>
      رفض
    Returns (verb, action_id, token). action_id/token may be "" for verb-only
    messages; the caller (bridge) resolves them from the stored pending action.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # Strip common emoji/punctuation that users append (e.g. "تأكيد ✓", "confirm ✅")
    import re as _re
    cleaned = _re.sub(r"[\U0001f000-\U0001ffff\u2600-\u27bf\u2b00-\u2bff\u2713\u2714\u2717\u2718\u2705\u274c\u274e\u2753\u2757\ufe0f\u200d\u2764\U0001f44d\U0001f44e\U0001f194\U0001f198]+", " ", raw).strip()
    parts = cleaned.replace("`", "").split()
    if not parts:
        return None
    verb = parts[0].lower()
    action_id = parts[1] if len(parts) >= 2 else ""
    token = parts[2] if len(parts) >= 3 else ""
    if verb in {"تأكيد", "تاكيد", "confirm", "yes", "موافق", "موافقة", "ok", "okay", "افق", "أوافق"}:
        # Verb-only confirmation is valid — the bridge resolves action_id/token
        # from the pending action stored in user_data.
        return ("confirm", action_id, token)
    if verb in {"رفض", "reject", "no", "الغاء", "إلغاء", "cancel", "لا"}:
        return ("reject", action_id, "")
    return None


def consume_execute_grant(state: AgentState, tool: str) -> bool:
    """Single-use grant after confirm — must match tool and be present."""
    grant = (state.extensions or {}).get("hitl_execute_grant")
    if not isinstance(grant, dict):
        return False
    if str(grant.get("tool") or "") != tool:
        return False
    if not grant.get("single_use"):
        return False
    # consume
    state.extensions.pop("hitl_execute_grant", None)
    state.extensions["hitl_confirmed"] = False
    pending = _load_pending(state)
    if pending:
        pending.status = "consumed"
        state.extensions["pending_action"] = pending.to_dict()
    state.record(AgentRole.HITL, "grant_consumed", tool)
    return True
