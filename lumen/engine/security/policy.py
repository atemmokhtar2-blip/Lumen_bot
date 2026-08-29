"""Policy engine — allow / deny / require confirmation. No side effects.

World-class default: **fail closed**. Unknown tools are DENY unless explicitly
listed in the allowlist (or constructor allowed_tools).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


@dataclass(frozen=True)
class ToolRequest:
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    confirmed: bool = False


@dataclass
class PolicyDecision:
    verdict: PolicyVerdict
    reason: str = ""
    redacted_params: Dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict == PolicyVerdict.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.verdict == PolicyVerdict.REQUIRE_CONFIRMATION


# Tools the platform actually implements (must stay in sync with tool_runtime)
_DEFAULT_ALLOWED: Set[str] = {
    "clone_repo",
    "create_repo",
    "git_push",
    "git_pull",
    "repo_inspect",
    "repo_understand",
    "repo_modify",
    "generate_bot",
    "refine_bot",
    "host_start",
    "host_stop",
    "host_status",
    "host_diagnose",
    "static_analysis",
    "package_health",
    # terminal_exec / deploy intentionally OMITTED — no safe host RCE surface
}

_CONFIRMATION_REQUIRED: Set[str] = {
    "git_push",
    "create_repo",
    "repo_modify",
    "host_start",
    "host_stop",
}


_HARD_DENY: Set[str] = {
    "terminal_exec",
    "deploy",
    "run_shell",
    "exec",
    "shell",
    "bash",
    "system",
}


class PolicyEngine:
    def __init__(
        self,
        *,
        denied_tools: Optional[Set[str]] = None,
        confirmation_required: Optional[Set[str]] = None,
        allowed_tools: Optional[Set[str]] = None,
        fail_closed: bool = True,
    ) -> None:
        self._denied = set(denied_tools or ())
        self._confirm = set(confirmation_required or _CONFIRMATION_REQUIRED)
        # None + fail_closed → use default allowlist; explicit set wins
        if allowed_tools is not None:
            self._allowed: Optional[Set[str]] = set(allowed_tools)
        elif fail_closed:
            self._allowed = set(_DEFAULT_ALLOWED)
        else:
            self._allowed = None  # legacy open mode (tests only)

    def evaluate(self, request: ToolRequest) -> PolicyDecision:
        name = (request.tool_name or "").strip()
        if not name:
            return PolicyDecision(PolicyVerdict.DENY, "empty tool name")
        if name in self._denied or name in _HARD_DENY:
            return PolicyDecision(PolicyVerdict.DENY, f"tool '{name}' denied (hard)")
        if self._allowed is not None and name not in self._allowed:
            return PolicyDecision(
                PolicyVerdict.DENY,
                f"tool '{name}' not in allowlist (fail-closed)",
            )
        if name in self._confirm and not request.confirmed:
            return PolicyDecision(
                PolicyVerdict.REQUIRE_CONFIRMATION,
                f"tool '{name}' requires confirmation",
                redacted_params=_redact(request.params),
            )
        return PolicyDecision(
            PolicyVerdict.ALLOW, "ok", redacted_params=_redact(request.params)
        )


def _redact(params: Dict[str, Any]) -> Dict[str, Any]:
    sensitive = {"token", "password", "secret", "api_key", "pat", "authorization"}
    return {
        k: ("***REDACTED***" if any(s in k.lower() for s in sensitive) else v)
        for k, v in (params or {}).items()
    }


__all__ = [
    "PolicyVerdict",
    "ToolRequest",
    "PolicyDecision",
    "PolicyEngine",
    "_DEFAULT_ALLOWED",
]
