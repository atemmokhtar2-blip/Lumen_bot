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
    # Exfiltration: block when user explicitly asks to PRINT/LEAK/SEND
    # secrets to an external destination. Legitimate code patterns like
    # `print("Error: TELEGRAM_BOT_TOKEN not found")` or `os.getenv('TOKEN')`
    # must NOT be blocked — those are standard bot setup patterns.
    # Strategy: match exfiltration VERB + secret keyword, but EXCLUDE when
    # the context is clearly a standard error-guard pattern (print + "not found" / "missing" / "required").
    ("exfil_env", re.compile(
        r"(?i)\b(?:leak|exfiltrate|dump|reveal|expose|send|post|upload|transmit|print|show)\b"
        r".{0,50}\b(?:api[_-]?key|api[_-]?secret|access[_-]?token|TELEGRAM_BOT_TOKEN|"
        r"GEMINI_API_KEY|bot[_-]?token|secret[_-]?key|private[_-]?key|api\s+key|secrets?|passwords?|"
        r"environment\s+variables?|env\s+vars?)\b"
        r"(?!.{0,30}(?:not\s+found|missing|required|not\s+set|environment\s+variable\s+should|not\s+in|is\s+none|"
        r"from\s+environment|os\.getenv|getenv|environ|\.env|set\s+the|configure|setup|"
        r"not\s+configured|please\s+set|must\s+be\s+set))"
    )),
    # Second pattern: explicit "send/leak/upload secret to URL/endpoint/webhook"
    ("exfil_send", re.compile(
        r"(?i)\b(?:send|leak|upload|post|transmit|exfiltrate|dump)\b"
        r".{0,60}\b(?:api[_-]?key|token|secret|TELEGRAM_BOT|GEMINI_API|bot[_-]?token|secrets?|passwords?)\b"
        r".{0,40}\b(?:to|via|through)\b.{0,30}\b(?:url|webhook|endpoint|http|server|chat|channel|chat_id|user|evil|attacker)\b",
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


def scan_user_request_only(text: str) -> PromptGuardResult:
    """Scan only the user's original request (first line/paragraph before ---).

    Used by agent_loop to avoid false-positives from repo context / agent
    generated code that gets appended to the goal text on retries.
    """
    raw = (text or "").strip()
    if not raw:
        return PromptGuardResult(ok=False, reasons=["empty_request"], sanitized="")
    # Extract only the portion before the first "---" separator (task packet marker)
    # or before "TARGET FILES:" / "ACCEPTANCE CRITERIA:" / "REPO CONTEXT:" etc.
    markers = ["\n---\n", "\nTARGET FILES:", "\nACCEPTANCE CRITERIA:",
               "\nREPO CONTEXT:", "\nSYMBOL OUTLINE", "\nBLAST RADIUS",
               "\nCONSTRAINTS:", "\nHARD GATE:"]
    cut = len(raw)
    for m in markers:
        idx = raw.find(m)
        if idx != -1 and idx < cut:
            cut = idx
    user_part = raw[:cut].strip()
    return sanitize_generation_prompt(user_part)
