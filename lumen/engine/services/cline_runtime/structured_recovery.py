"""Structured recovery for the Cline agent loop (Phase-2).

Replaces "LLM sees error and hopes" with typed policies:
  - network/git/host failures → limited retry + backoff + strategy hint
  - write/edit failures → force read_file then partial patch
  - parse failures → ultra-short repair prompt (no full history resend)

No LangGraph. Same model via decide(); recovery uses a tight message window.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Tool categories for recovery policy
_NETWORK_TOOLS = frozenset({
    "run_shell", "browser_navigate", "browser_click", "browser_fill",
    "run_skill",
})
# shell often wraps git/clone/host; classify by error text too
_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "apply_edits", "apply_patch", "search_replace",
})
_PARSE_SENTINEL = "parse_fail"

_DEFAULT_MAX_TOTAL = 4          # total recovery attempts per agent run
_DEFAULT_MAX_PER_KEY = 2        # per tool-fingerprint / category key


@dataclass
class RecoveryAction:
    """What the loop should do next for a failed step."""
    mode: str  # network_retry | force_read_patch | parse_repair | none
    prompt: str
    backoff_sec: float = 0.0
    force_tool: str | None = None  # soft hint, not enforced by runtime
    key: str = ""
    category: str = ""


@dataclass
class StructuredRecovery:
    """Tracks recovery attempts and builds policy-driven repair actions."""

    max_total: int = _DEFAULT_MAX_TOTAL
    max_per_key: int = _DEFAULT_MAX_PER_KEY
    total_attempts: int = 0
    per_key: dict[str, int] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "max_total": self.max_total,
            "max_per_key": self.max_per_key,
            "total_attempts": self.total_attempts,
            "per_key": dict(self.per_key),
            "history": list(self.history)[-20:],
            "exhausted": self.total_attempts >= self.max_total,
        }

    def _classify(self, tool: str | None, result: dict[str, Any] | None, *, parse_fail: bool = False) -> str:
        if parse_fail:
            return "parse"
        tool_s = str(tool or "")
        err = str((result or {}).get("error") or (result or {}).get("message") or "").lower()
        if tool_s in _WRITE_TOOLS or any(x in err for x in ("write", "edit", "patch", "file not", "enoent", "permission denied")):
            if tool_s in _WRITE_TOOLS:
                return "write"
        if tool_s in _NETWORK_TOOLS or any(
            x in err for x in ("timeout", "timed out", "connection", "network", "403", "401", "502", "503", "git ", "clone", "host", "econn", "dns")
        ):
            return "network"
        if tool_s in _WRITE_TOOLS:
            return "write"
        if tool_s in _NETWORK_TOOLS:
            return "network"
        return "generic"

    def _key(self, category: str, tool: str | None, args: dict[str, Any] | None) -> str:
        path = ""
        if isinstance(args, dict):
            path = str(args.get("path") or args.get("file") or args.get("command") or args.get("cmd") or "")[:120]
        return f"{category}:{tool or '-'}:{path}"

    def can_attempt(self, key: str) -> bool:
        if self.total_attempts >= self.max_total:
            return False
        if int(self.per_key.get(key) or 0) >= self.max_per_key:
            return False
        return True

    def plan(
        self,
        *,
        tool: str | None,
        args: dict[str, Any] | None,
        result: dict[str, Any] | None,
        parse_fail: bool = False,
        parse_err: str = "",
    ) -> RecoveryAction | None:
        """Return a recovery action or None if exhausted / not applicable."""
        result = result or {}
        if not parse_fail and result.get("ok"):
            return None

        category = self._classify(tool, result, parse_fail=parse_fail)
        key = self._key(category, tool, args)
        if not self.can_attempt(key):
            logger.info("recovery exhausted for key=%s total=%d", key, self.total_attempts)
            return None

        err = str(result.get("error") or result.get("message") or parse_err or "unknown")[:300]
        path = ""
        if isinstance(args, dict):
            path = str(args.get("path") or args.get("file") or "")[:200]

        if category == "parse":
            action = RecoveryAction(
                mode="parse_repair",
                category=category,
                key=key,
                prompt=(
                    "PARSE REPAIR ONLY. Reply with ONE JSON object, nothing else:\n"
                    '{"thought":"fix parse","tool":"list_dir","args":{"path":"."},"finish":false,"summary":""}\n'
                    f"Prior error: {err[:120]}"
                ),
            )
        elif category == "write":
            target = path or "."
            action = RecoveryAction(
                mode="force_read_patch",
                category=category,
                key=key,
                force_tool="read_file",
                prompt=(
                    "WRITE RECOVERY: previous write/edit failed. "
                    f"1) call read_file on path={target!r} "
                    "2) then edit_file or apply_patch with a MINIMAL partial fix only. "
                    "Do not rewrite the whole file. "
                    f"Error: {err[:160]}"
                ),
            )
        elif category == "network":
            attempt_n = int(self.per_key.get(key) or 0) + 1
            backoff = min(1.5 * attempt_n, 4.0)
            action = RecoveryAction(
                mode="network_retry",
                category=category,
                key=key,
                backoff_sec=backoff,
                prompt=(
                    "NETWORK/SHELL RECOVERY: prior call failed. "
                    f"Retry with a different strategy (attempt {attempt_n}). "
                    "Prefer a smaller command, check cwd with list_dir, avoid repeating the exact same command. "
                    f"Error: {err[:160]}"
                ),
            )
        else:
            action = RecoveryAction(
                mode="generic",
                category=category,
                key=key,
                prompt=(
                    f"STEP RECOVERY: tool={tool} failed ({err[:140]}). "
                    "Fix this single step only. Prefer read_file before write. JSON tool call only."
                ),
            )

        return action

    def commit(self, action: RecoveryAction) -> None:
        """Record that a recovery action was applied."""
        self.total_attempts += 1
        self.per_key[action.key] = int(self.per_key.get(action.key) or 0) + 1
        self.history.append({
            "key": action.key,
            "mode": action.mode,
            "category": action.category,
            "total": self.total_attempts,
            "per_key": self.per_key[action.key],
        })

    def recovery_system_prompt(self) -> str:
        return (
            "You are a recovery sub-agent. Fix ONLY the failed step. "
            "Do not re-plan the whole project. "
            "Respond with one JSON tool call. Prefer the smallest safe fix."
        )

    def build_recovery_messages(
        self,
        *,
        action: RecoveryAction,
        tool: str | None,
        args: dict[str, Any] | None,
        result: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Minimal message window for recovery decide() — no full history."""
        import json as _json
        safe_args = {}
        if isinstance(args, dict):
            for k, v in args.items():
                if k == "content" and isinstance(v, str) and len(v) > 200:
                    safe_args[k] = v[:200] + f"...({len(v)} chars)"
                else:
                    safe_args[k] = v
        err_body = {
            "tool": tool,
            "args": safe_args,
            "result": {
                "ok": bool((result or {}).get("ok")),
                "error": str((result or {}).get("error") or "")[:400],
                "message": str((result or {}).get("message") or "")[:400],
            },
        }
        return [
            {"role": "system", "content": self.recovery_system_prompt()},
            {
                "role": "user",
                "content": action.prompt + "\n\nFAILED_STEP:\n" + _json.dumps(err_body, ensure_ascii=False)[:1800],
            },
        ]


__all__ = ["StructuredRecovery", "RecoveryAction"]
