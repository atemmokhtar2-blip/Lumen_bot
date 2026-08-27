"""Sanitize generation requests against prompt injection and secret exfiltration.

Single authoritative guard for Telegram + agent_loop + run_generation.
Defense-in-depth alongside ValidateBlueprintStage / isolation policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("os_system", re.compile(r"\bos\.system\s*\(", re.I)),
    ("eval_call", re.compile(r"(?<![A-Za-z_])eval\s*\(", re.I)),
    ("exec_call", re.compile(r"(?<![A-Za-z_])exec\s*\(", re.I)),
    ("subprocess_shell", re.compile(r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True", re.I)),
    ("compile_exec", re.compile(r"\bcompile\s*\([^)]*\)\s*\Z|__import__\s*\(\s*['\"]os['\"]", re.I)),
    ("dunder_import", re.compile(r"__import__\s*\(", re.I)),
    ("pickle_loads", re.compile(r"pickle\.loads\s*\(", re.I)),
    ("pty_spawn", re.compile(r"\bpty\.spawn\s*\(", re.I)),
    ("ignore_prev", re.compile(
        r"(ignore|disregard)\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|constraints)",
        re.I,
    )),
    ("ignore_system", re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions")),
    ("jailbreak_role", re.compile(
        r"(you\s+are\s+now\s+unrestricted|jailbreak|DAN\s+mode|developer\s+mode\s+enabled)",
        re.I,
    )),
    ("role_hijack", re.compile(r"(?i)you\s+are\s+now\s+(a|an|the)\s+")),
    ("exfil_env", re.compile(
        r"(?i)(print|show|dump|leak|reveal).{0,40}(api[_-]?key|token|secret|TELEGRAM_BOT|GEMINI_API)",
    )),
    ("tool_abuse", re.compile(r"(?i)(run_shell|browser_navigate)\s*\(.*rm\s+-rf")),
    ("write_malware", re.compile(
        r"(generate|emit|write|include)\s+.{0,40}(reverse\s*shell|rm\s+-rf\s+/|curl\s+[^\n]*\|\s*sh)",
        re.I,
    )),
]


@dataclass
class PromptGuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    sanitized: str = ""
    backend: str = "prompt_guard"


def sanitize_generation_prompt(text: str, *, max_len: int = 8000) -> PromptGuardResult:
    """Return ok=False when the request looks like injection / system-abuse."""
    raw = (text or "").strip()
    if not raw:
        return PromptGuardResult(ok=False, reasons=["empty_request"], sanitized="")
    if len(raw) > max_len:
        raw = raw[:max_len]
    reasons: list[str] = []
    for code, pat in _INJECTION_PATTERNS:
        if pat.search(raw):
            reasons.append(code)
    cleaned = raw.replace("\x00", " ").replace("\r", "\n")
    cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    return PromptGuardResult(ok=not reasons, reasons=reasons, sanitized=cleaned)


def scan_user_input(text: str) -> PromptGuardResult:
    """Public entry used by run_generation / agent_loop (single path)."""
    return sanitize_generation_prompt(text)
