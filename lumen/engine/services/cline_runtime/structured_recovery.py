"""Structured recovery for the Cline agent loop (Phase-2).

Replaces "LLM sees error and hopes" with typed, enforced policies:
  - network/git/host/shell failures → limited retry + backoff + strategy change
  - write/edit failures → ENFORCED read_file then partial patch (sub-agent)
  - parse failures → ultra-short repair prompt (no full history resend)

No LangGraph. Recovery sub-agent uses the same model via decide() with a
dedicated system prompt and a minimal message window.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Explicit tool names (agent_fs + tool_runtime surface)
_NETWORK_TOOLS = frozenset({
    "run_shell",
    "browser_navigate", "browser_click", "browser_fill",
    "run_skill",
    "clone_repo", "git_push", "git_pull", "create_repo",
    "host_start", "host_stop", "host_status", "host_logs",
})
_WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "apply_edits", "apply_patch", "search_replace",
})
_NETWORK_ERR = (
    "timeout", "timed out", "connection", "network", "403", "401", "502", "503",
    "git ", "clone", "host", "econn", "dns", "permission denied", "could not resolve",
    "ssh", "auth", "unauthorized", "rate limit", "429",
)

_DEFAULT_MAX_TOTAL = 4
_DEFAULT_MAX_PER_KEY = 2


@dataclass
class RecoveryAction:
    """What the loop must do for a failed step."""

    mode: str  # network_retry | force_read_patch | parse_repair | generic
    prompt: str
    backoff_sec: float = 0.0
    force_tool: str | None = None
    force_args: dict[str, Any] = field(default_factory=dict)
    strategy: str = ""  # e.g. simplify_shell | read_then_patch | short_parse
    key: str = ""
    category: str = ""


@dataclass
class StructuredRecovery:
    """Tracks recovery_attempts and builds enforced policy actions."""

    max_total: int = _DEFAULT_MAX_TOTAL
    max_per_key: int = _DEFAULT_MAX_PER_KEY
    total_attempts: int = 0
    per_key: dict[str, int] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "max_total": self.max_total,
            "max_per_key": self.max_per_key,
            "recovery_attempts": self.total_attempts,
            "total_attempts": self.total_attempts,
            "per_key": dict(self.per_key),
            "history": list(self.history)[-20:],
            "exhausted": self.total_attempts >= self.max_total,
        }

    def _classify(
        self,
        tool: str | None,
        result: dict[str, Any] | None,
        *,
        parse_fail: bool = False,
    ) -> str:
        if parse_fail:
            return "parse"
        tool_s = str(tool or "").strip()
        err = str(
            (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("stderr")
            or ""
        ).lower()
        if tool_s in _WRITE_TOOLS:
            return "write"
        if tool_s in _NETWORK_TOOLS:
            return "network"
        if any(x in err for x in _NETWORK_ERR):
            return "network"
        if any(x in err for x in ("write", "edit", "patch", "enoent", "file not", "is a directory")):
            return "write"
        return "generic"

    def _key(self, category: str, tool: str | None, args: dict[str, Any] | None) -> str:
        path = ""
        if isinstance(args, dict):
            path = str(
                args.get("path")
                or args.get("file")
                or args.get("url")
                or args.get("command")
                or args.get("cmd")
                or ""
            )[:120]
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
        category = self._classify(tool, result, parse_fail=parse_fail)
        key = self._key(category, tool, args)
        if not self.can_attempt(key):
            return None

        err = str(
            parse_err
            or (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("stderr")
            or "unknown"
        )
        args = dict(args or {})
        attempt_n = int(self.per_key.get(key) or 0) + 1

        if category == "parse":
            return RecoveryAction(
                mode="parse_repair",
                category="parse",
                key=key,
                strategy="short_parse",
                prompt=(
                    "PARSE REPAIR ONLY. Reply with ONE JSON object, nothing else:\n"
                    '{"thought":"fix parse","tool":"list_dir","args":{"path":"."},'
                    '"finish":false,"summary":""}\n'
                    f"Prior error: {err[:100]}"
                ),
            )

        if category == "write":
            target = str(args.get("path") or args.get("file") or "").strip() or "."
            return RecoveryAction(
                mode="force_read_patch",
                category="write",
                key=key,
                strategy="read_then_patch",
                force_tool="read_file",
                force_args={"path": target},
                prompt=(
                    "WRITE RECOVERY (enforced): read_file already applied on the target. "
                    f"Now edit_file or apply_patch path={target!r} with a MINIMAL partial fix only. "
                    "Do not rewrite the whole file. Do not call write_file for an existing file. "
                    f"Error: {err[:160]}"
                ),
            )

        if category == "network":
            backoff = min(1.5 * attempt_n, 4.0)
            # Strategy change: simplify shell commands on retry
            strategy = "backoff_retry"
            strategy_hint = (
                "Retry with a different strategy: smaller command, list_dir/cwd first, "
                "no identical command."
            )
            cmd = str(args.get("command") or args.get("cmd") or "")
            if tool == "run_shell" and cmd:
                strategy = "simplify_shell"
                strategy_hint = (
                    "SHELL STRATEGY CHANGE: do not repeat the same command. "
                    "First list_dir or a cheaper probe, then a simpler command. "
                    f"Failed command was: {cmd[:120]}"
                )
            elif str(tool or "").startswith("git") or tool == "clone_repo":
                strategy = "git_retry"
                strategy_hint = (
                    "GIT/CLONE STRATEGY CHANGE: verify URL/permissions; prefer shallow clone; "
                    "do not repeat the identical call."
                )
            elif str(tool or "").startswith("host"):
                strategy = "host_retry"
                strategy_hint = (
                    "HOST STRATEGY CHANGE: check status before start; avoid duplicate host_start."
                )
            return RecoveryAction(
                mode="network_retry",
                category="network",
                key=key,
                strategy=strategy,
                backoff_sec=backoff,
                prompt=(
                    f"NETWORK RECOVERY (attempt {attempt_n}): {strategy_hint} "
                    f"Error: {err[:160]}"
                ),
            )

        return RecoveryAction(
            mode="generic",
            category=category,
            key=key,
            strategy="generic_fix",
            prompt=(
                f"STEP RECOVERY: tool={tool} failed ({err[:140]}). "
                "Fix this single step only. Prefer read_file before write. JSON tool call only."
            ),
        )

    def commit(self, action: RecoveryAction) -> None:
        self.total_attempts += 1
        self.per_key[action.key] = int(self.per_key.get(action.key) or 0) + 1
        self.history.append({
            "key": action.key,
            "mode": action.mode,
            "category": action.category,
            "strategy": action.strategy,
            "recovery_attempts": self.total_attempts,
            "per_key": self.per_key[action.key],
            "force_tool": action.force_tool,
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
        enforced_read: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Minimal message window for recovery decide() — no full history."""
        safe_args: dict[str, Any] = {}
        if isinstance(args, dict):
            for k, v in args.items():
                if k == "content" and isinstance(v, str) and len(v) > 200:
                    safe_args[k] = v[:200] + f"...({len(v)} chars)"
                else:
                    safe_args[k] = v
        err_body: dict[str, Any] = {
            "tool": tool,
            "args": safe_args,
            "result": {
                "ok": bool((result or {}).get("ok")),
                "error": str((result or {}).get("error") or "")[:400],
                "message": str((result or {}).get("message") or "")[:400],
            },
        }
        if enforced_read is not None:
            err_body["enforced_read_file"] = {
                "ok": bool(enforced_read.get("ok")),
                "path": enforced_read.get("path"),
                "content_head": str(enforced_read.get("content") or enforced_read.get("data") or "")[:800],
            }
        return [
            {"role": "system", "content": self.recovery_system_prompt()},
            {
                "role": "user",
                "content": (
                    action.prompt
                    + "\n\nFAILED_STEP:\n"
                    + json.dumps(err_body, ensure_ascii=False)[:2000]
                ),
            },
        ]


def network_retry_params(tool: str, params: dict[str, Any] | None, strategy: str) -> dict[str, Any]:
    """Mutate params for a concrete network/git/host retry (tool_runtime path)."""
    p = dict(params or {})
    tool = (tool or "").strip()
    if tool == "clone_repo":
        # Strategy change: force shallow, drop branch pin on retry
        p["depth"] = 1
        p.pop("branch", None)
        p["_recovery_strategy"] = strategy or "git_retry"
    elif tool in {"git_pull", "git_push"}:
        p["_recovery_strategy"] = strategy or "git_retry"
    elif tool.startswith("host"):
        p["_recovery_strategy"] = strategy or "host_retry"
    elif tool == "run_shell":
        # Do not auto-rewrite commands; mark recovery only
        p["_recovery_strategy"] = strategy or "simplify_shell"
    else:
        p["_recovery_strategy"] = strategy or "backoff_retry"
    return p


__all__ = ["StructuredRecovery", "RecoveryAction", "network_retry_params"]

