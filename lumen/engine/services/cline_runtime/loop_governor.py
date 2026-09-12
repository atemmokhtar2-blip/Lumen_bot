"""Agent loop governor — step budgets, empty-loop detection, fingerprints."""
from __future__ import annotations

import json
import logging
import os
import time as _time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _band_limits(band: str) -> dict[str, int]:
    band = (band or "medium").strip().lower()
    if band == "easy":
        return {
            "max_steps": 5,  # 4–6
            "history_keep_start": 8, "history_keep_end": 4,
            "prompt_chars_start": 10000, "prompt_chars_end": 6000,
            "no_progress_limit": 2,
        }
    if band == "hard":
        return {
            "max_steps": 14,  # 12–15
            "history_keep_start": 12, "history_keep_end": 6,
            "prompt_chars_start": 15000, "prompt_chars_end": 8000,
            "no_progress_limit": 4,
        }
    return {
        "max_steps": 9,  # 8–10
        "history_keep_start": 10, "history_keep_end": 5,
        "prompt_chars_start": 12000, "prompt_chars_end": 7000,
        "no_progress_limit": 3,
    }


def _tool_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Stable fingerprint for repeated-tool detection (path/command first)."""
    args = dict(args or {})
    try:
        identity: dict[str, Any] = {"tool": str(tool or "")}
        for key in (
            "path", "file", "target", "name", "command", "cmd",
            "query", "pattern", "glob", "url",
        ):
            if key in args and args[key] is not None:
                identity[key] = str(args[key])[:200]
        content = args.get("content")
        if isinstance(content, str) and content:
            identity["content_len"] = len(content)
            identity["content_head"] = content[:80]
        if len(identity) <= 1:
            identity["keys"] = sorted(str(k) for k in args.keys())
        return json.dumps(identity, sort_keys=True, ensure_ascii=False)[:500]
    except Exception:
        return f"{tool}:{sorted(str(k) for k in args.keys())}"


@dataclass
class LoopGovernor:
    """Explicit controller for the agent loop (Phase-1).

    Owns: dynamic step budget, progressive context caps, empty-loop detection
    (repeated tool + no-progress), and the authoritative loop_governor report.
    """

    band: str
    difficulty_score: float | None
    max_steps: int
    source: str
    env_ceiling: int
    history_keep_start: int
    history_keep_end: int
    prompt_chars_start: int
    prompt_chars_end: int
    repeated_tool_limit: int = 3
    no_progress_limit: int = 3

    # runtime
    step_index: int = 0
    last_fingerprint: str | None = None
    repeat_count: int = 0
    no_progress_streak: int = 0
    files_at_last_progress: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens_est: int = 0
    steps_log: list = field(default_factory=list)
    stop_reason_detail: dict | None = None
    loop_start: float = 0.0

    _INSPECT_TOOLS: frozenset = frozenset({
        "list_dir", "tree", "read_file", "read_files", "grep_codebase",
        "glob_files", "find_symbol", "get_symbol_source", "find_references",
        "blast_radius", "code_search", "browser_content", "browser_screenshot",
    })

    @classmethod
    def from_difficulty(
        cls,
        diff: dict[str, Any] | None,
        *,
        explicit_max_steps: int | None = None,
    ) -> "LoopGovernor":
        band = str((diff or {}).get("band") or "medium").strip().lower()
        limits = _band_limits(band)
        # Single source: loop_support.env_max_steps_ceiling()
        from .loop_support import env_max_steps_ceiling
        env_ceiling = int(env_max_steps_ceiling())
        if explicit_max_steps is not None:
            max_steps = max(1, min(int(explicit_max_steps), env_ceiling))
            source = "explicit_max_steps"
        else:
            max_steps = max(1, min(int(limits["max_steps"]), env_ceiling))
            source = f"band:{band}"
        return cls(
            band=band,
            difficulty_score=(diff or {}).get("score"),
            max_steps=max_steps,
            source=source,
            env_ceiling=env_ceiling,
            history_keep_start=int(limits["history_keep_start"]),
            history_keep_end=int(limits["history_keep_end"]),
            prompt_chars_start=int(limits["prompt_chars_start"]),
            prompt_chars_end=int(limits["prompt_chars_end"]),
            repeated_tool_limit=3,
            no_progress_limit=int(limits["no_progress_limit"]),
        )

    def start(self) -> None:
        self.loop_start = _time.monotonic()

    def context_caps(self) -> tuple[int, int]:
        """Progressive history_keep + prompt_max_chars for the current step."""
        limit = max(1, self.max_steps)
        if limit <= 1:
            return self.history_keep_end, self.prompt_chars_end
        ratio = max(0.0, min(1.0, float(self.step_index) / float(limit - 1)))
        keep = int(round(
            self.history_keep_start
            + (self.history_keep_end - self.history_keep_start) * ratio
        ))
        chars = int(round(
            self.prompt_chars_start
            + (self.prompt_chars_end - self.prompt_chars_start) * ratio
        ))
        return max(4, min(16, keep)), max(4000, min(20000, chars))

    def note_decide(
        self,
        *,
        tool: str | None,
        finish: bool,
        parse_ok: bool,
        usage: dict[str, Any] | None,
        history_keep: int,
        prompt_chars: int,
        cache_hit: bool = False,
    ) -> None:
        if usage:
            self.total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.total_completion_tokens += int(usage.get("completion_tokens") or 0)
            self.total_tokens_est += int(
                usage.get("total_tokens") or usage.get("prompt_tokens_est") or 0
            )
        self.steps_log.append({
            "step": self.step_index,
            "event": "decide",
            "tool": str(tool or ""),
            "finish": bool(finish),
            "parse_ok": bool(parse_ok),
            "history_keep": history_keep,
            "prompt_chars": prompt_chars,
            "cache_hit": bool(cache_hit),
            "elapsed_sec": round(_time.monotonic() - self.loop_start, 2) if self.loop_start else 0,
        })
        # Soft failures (no usable tool) count as no-progress
        if not finish and (not parse_ok or not tool):
            self.no_progress_streak += 1

    def check_repeated_tool(self, tool: str, args: dict[str, Any]) -> str | None:
        """Return stop reason if identical tool+args repeated too many times."""
        if not tool or tool == "finish":
            return None
        fp = _tool_fingerprint(tool, args)
        if fp and fp == self.last_fingerprint:
            self.repeat_count += 1
        else:
            self.repeat_count = 1
            self.last_fingerprint = fp
        if self.repeat_count >= self.repeated_tool_limit:
            self.stop_reason_detail = {
                "reason": "repeated_tool_loop",
                "tool": str(tool),
                "repeats": self.repeat_count,
                "fingerprint": (fp or "")[:200],
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_repeated_tool",
                "tool": str(tool),
                "repeats": self.repeat_count,
                "elapsed_sec": round(_time.monotonic() - self.loop_start, 2),
            })
            return "repeated_tool_loop"
        return None

    def note_blocked_step(self, *, tool: str | None, reason: str) -> str | None:
        """Record a step that did not execute a mutating tool (policy/parse block).

        Always counts as no-progress. Returns stop reason when limit hit.
        """
        tool_s = str(tool or "") or "blocked"
        self.no_progress_streak += 1
        self.steps_log.append({
            "step": self.step_index,
            "event": "blocked",
            "tool": tool_s,
            "reason": str(reason)[:120],
            "streak": self.no_progress_streak,
            "elapsed_sec": round(_time.monotonic() - self.loop_start, 2) if self.loop_start else 0,
        })
        if self.no_progress_streak >= self.no_progress_limit and self.step_index >= 1:
            self.stop_reason_detail = {
                "reason": "no_progress",
                "streak": self.no_progress_streak,
                "limit": self.no_progress_limit,
                "last_tool": tool_s,
                "blocked_reason": str(reason)[:120],
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_no_progress",
                "streak": self.no_progress_streak,
                "tool": tool_s,
                "via": "blocked",
            })
            return "no_progress"
        return None

    def note_tool_result(
        self,
        *,
        tool: str | None,
        result: dict[str, Any] | None,
        files_written: list[str],
    ) -> str | None:
        """Update progress tracking. Return stop reason on no-progress limit."""
        result = result or {}
        tool_s = str(tool or "")
        mutating = tool_s not in self._INSPECT_TOOLS and tool_s not in {"", "finish"}
        new_files = len(files_written) > self.files_at_last_progress
        tool_ok = bool(result.get("ok"))
        progress = new_files or (
            mutating
            and tool_ok
            and tool_s in {
                "write_file", "edit_file", "apply_edits", "apply_patch",
                "search_replace", "run_shell",
            }
        )
        if progress:
            self.no_progress_streak = 0
            self.files_at_last_progress = len(files_written)
        elif tool_s not in {"", "finish"}:
            self.no_progress_streak += 1

        if self.no_progress_streak >= self.no_progress_limit and self.step_index >= 1:
            self.stop_reason_detail = {
                "reason": "no_progress",
                "streak": self.no_progress_streak,
                "limit": self.no_progress_limit,
                "files_written": len(files_written),
                "last_tool": tool_s,
                "step": self.step_index,
            }
            self.steps_log.append({
                "step": self.step_index,
                "event": "hard_stop_no_progress",
                "streak": self.no_progress_streak,
                "tool": tool_s,
                "files_written": len(files_written),
                "elapsed_sec": round(_time.monotonic() - self.loop_start, 2),
            })
            return "no_progress"
        return None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "band": self.band,
            "difficulty_score": self.difficulty_score,
            "max_steps": self.max_steps,
            "source": self.source,
            "env_ceiling": self.env_ceiling,
            "history_keep_start": self.history_keep_start,
            "history_keep_end": self.history_keep_end,
            "prompt_chars_start": self.prompt_chars_start,
            "prompt_chars_end": self.prompt_chars_end,
            "repeated_tool_limit": self.repeated_tool_limit,
            "no_progress_limit": self.no_progress_limit,
            "no_progress_streak": self.no_progress_streak,
            "repeat_count": self.repeat_count,
            "step_index": self.step_index,
            "steps_log": list(self.steps_log)[-60:],
            "stop_reason_detail": self.stop_reason_detail,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens_est": self.total_tokens_est,
        }


    def finalize(self, state: "AgentState") -> None:
        meta = self.to_metadata()
        meta["final_steps"] = len(state.steps)
        meta["final_stop_reason"] = state.stop_reason
        meta["final_ok"] = bool(state.ok)
        meta["elapsed_sec"] = (
            round(_time.monotonic() - self.loop_start, 2) if self.loop_start else None
        )
        if not meta.get("stop_reason_detail") and state.stop_reason:
            meta["stop_reason_detail"] = {"reason": state.stop_reason}
        keep, chars = self.context_caps()
        meta["final_history_keep"] = keep
        meta["final_prompt_chars"] = chars
        state.metadata["loop_governor"] = meta
