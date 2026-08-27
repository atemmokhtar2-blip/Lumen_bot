"""LLM input/output guardrails — real defense against prompt injection & data leaks.

Priority order:
  1) llm-guard (ProtectAI) when installed and LLM_GUARD_ENABLED=1
  2) Built-in prompt_guard patterns (always available)

This is not a mock: when llm-guard is present, scanners run for granted.
When absent, fail-closed only if LLM_GUARD_REQUIRED=1; else pattern layer.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    sanitized: str = ""
    backend: str = "none"


def _enabled() -> bool:
    return (os.getenv("LLM_GUARD_ENABLED") or "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _required() -> bool:
    return (os.getenv("LLM_GUARD_REQUIRED") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _builtin_scan(text: str) -> GuardResult:
    from lumen.engine.pipeline.prompt_guard import sanitize_generation_prompt

    r = sanitize_generation_prompt(text or "")
    reasons = list(getattr(r, "reasons", None) or [])
    # Extra high-signal injection / exfil patterns
    raw = text or ""
    extra = [
        ("ignore_system", re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions")),
        ("exfil_env", re.compile(r"(?i)(print|show|dump|leak).{0,40}(api[_-]?key|token|secret|TELEGRAM_BOT)")),
        ("role_hijack", re.compile(r"(?i)you\s+are\s+now\s+(a|an|the)\s+")),
        ("tool_abuse", re.compile(r"(?i)(run_shell|browser_navigate)\s*\(.*rm\s+-rf")),
    ]
    for code, pat in extra:
        if pat.search(raw):
            reasons.append(code)
    return GuardResult(
        ok=not reasons,
        reasons=reasons,
        sanitized=getattr(r, "sanitized", None) or raw,
        backend="prompt_guard",
    )


def _llm_guard_scan(text: str) -> GuardResult | None:
    """Run ProtectAI llm-guard scanners when package is installed."""
    try:
        from llm_guard import scan_prompt  # type: ignore
        from llm_guard.input_scanners import (  # type: ignore
            PromptInjection,
            Secrets,
            TokenLimit,
        )
    except Exception:
        return None
    try:
        scanners = [
            PromptInjection(threshold=float(os.getenv("LLM_GUARD_INJECTION_THRESHOLD") or "0.75")),
            Secrets(),
            TokenLimit(limit=int(os.getenv("LLM_GUARD_TOKEN_LIMIT") or "4096")),
        ]
        sanitized, results_valid, results_score = scan_prompt(scanners, text or "")
        reasons: list[str] = []
        if isinstance(results_valid, dict):
            for name, valid in results_valid.items():
                if not valid:
                    score = (results_score or {}).get(name)
                    reasons.append(f"llm_guard:{name}:{score}")
        elif results_valid is False:
            reasons.append("llm_guard:rejected")
        # llm-guard convention: block if any scanner invalid
        if isinstance(results_valid, dict) and any(v is False for v in results_valid.values()):
            if not reasons:
                reasons.append("llm_guard:rejected")
        return GuardResult(
            ok=not reasons,
            reasons=reasons,
            sanitized=str(sanitized if sanitized is not None else text),
            backend="llm_guard",
        )
    except Exception as exc:
        logger.warning("llm_guard scan failed: %s", type(exc).__name__)
        return None


def scan_user_input(text: str) -> GuardResult:
    """Scan untrusted user text before agent / generation."""
    if not _enabled():
        return GuardResult(ok=True, sanitized=text or "", backend="disabled")
    # Always run builtin first (cheap)
    builtin = _builtin_scan(text)
    if not builtin.ok:
        return builtin
    # Strong layer when available
    strong = _llm_guard_scan(text)
    if strong is not None:
        return strong
    if _required():
        return GuardResult(
            ok=False,
            reasons=["llm_guard_required_but_unavailable"],
            sanitized=builtin.sanitized,
            backend="required_missing",
        )
    return builtin


def scan_model_output(text: str) -> GuardResult:
    """Light scan of model/tool output for secret leakage."""
    if not _enabled():
        return GuardResult(ok=True, sanitized=text or "", backend="disabled")
    raw = text or ""
    reasons: list[str] = []
    if re.search(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", raw):
        reasons.append("telegram_token_in_output")
    if re.search(r"\b(ghp_|sk-|gsk_|AQ\.)[A-Za-z0-9_\-]{16,}\b", raw):
        reasons.append("api_key_in_output")
    try:
        from llm_guard.output_scanners import Sensitive  # type: ignore
        from llm_guard import scan_output  # type: ignore

        sanitized, results_valid, _ = scan_output([Sensitive()], "", raw)
        if isinstance(results_valid, dict) and any(not v for v in results_valid.values()):
            reasons.append("llm_guard_output_sensitive")
        raw = str(sanitized if sanitized is not None else raw)
    except Exception:
        pass
    return GuardResult(ok=not reasons, reasons=reasons, sanitized=raw, backend="output")
