"""
Dynamic tools.py emission.

For each tool/command in THIS contract, ask the AI (Groq/HF) to write a pure
Python function body from the user description — no saved domain catalogs.

If AI is unavailable or returns unsafe/invalid code, fall back to a minimal
record stub for that tool id only.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from ..inference.engine import InferenceResult

logger = logging.getLogger("ai_agent_7h_bot.tools_emit")

_FORBIDDEN = re.compile(
    r"\b(eval|exec|__import__|subprocess|os\.system|os\.popen|pickle|socket\.socket|"
    r"ctypes|pty|commands\.|importlib)\b",
    re.I,
)


def _safe_ident(tid: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (tid or "").strip().lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "tool_" + (s or "x")
    return s[:48]


def _collect_tools(inf: InferenceResult) -> list[dict[str, Any]]:
    tools = [t for t in (getattr(inf, "dynamic_tools", None) or []) if isinstance(t, dict)]
    seen = {str(t.get("id") or "").lower() for t in tools}
    for c in getattr(inf, "commands", None) or []:
        name = (getattr(c, "name", None) or "").strip().lower()
        if not name or name in ("start", "help") or name in seen:
            continue
        tools.append({
            "id": name,
            "title": getattr(c, "description", None) or name,
            "input": "value",
            "source": "command",
        })
        seen.add(name)
    return tools


def _stub_body(tid: str) -> str:
    return (
        f"    return {{'ok': True, 'action': {tid!r}, 'input': (target or '')[:2000]}}\n"
    )


def _extract_function_body(code: str, tid: str) -> str | None:
    """Accept full def or bare body; return indented body lines ending with return."""
    text = (code or "").strip()
    if not text:
        return None
    # strip markdown fences
    text = re.sub(r"^```(?:python)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text.strip())
    if _FORBIDDEN.search(text):
        return None
    # If model returned full function, take body
    m = re.search(
        rf"def\s+tool_{re.escape(tid)}\s*\([^)]*\)\s*(?:->\s*[^:]+)?:\s*\n([\s\S]+)",
        text,
    )
    if not m:
        m = re.search(r"def\s+\w+\s*\([^)]*\)\s*(?:->\s*[^:]+)?:\s*\n([\s\S]+)", text)
    body = m.group(1) if m else text
    # normalize indent to 4 spaces
    lines = body.splitlines()
    cleaned: list[str] = []
    for ln in lines:
        if not ln.strip():
            cleaned.append("")
            continue
        # drop module-level imports of forbidden style already checked
        if re.match(r"^\s*import\s+os\b", ln) or re.match(r"^\s*from\s+os\b", ln):
            return None
        cleaned.append(ln)
    # ensure body is indented
    out_lines: list[str] = []
    for ln in cleaned:
        if not ln.strip():
            out_lines.append("")
            continue
        if ln.startswith("    "):
            out_lines.append(ln)
        elif ln.startswith("\t"):
            out_lines.append("    " + ln[1:])
        else:
            out_lines.append("    " + ln)
    body_txt = "\n".join(out_lines).rstrip() + "\n"
    # must look like python with a return
    if "return" not in body_txt:
        body_txt += "    return {'ok': True, 'action': %r, 'input': (target or '')[:2000]}\n" % tid
    # syntax check wrapped function
    wrapped = f"def tool_{tid}(target: str = '') -> dict:\n{body_txt}"
    try:
        compile(wrapped, f"<tool_{tid}>", "exec")
    except SyntaxError:
        return None
    if _FORBIDDEN.search(body_txt):
        return None
    return body_txt


def _ai_generate_body(tid: str, title: str, user_text: str, timeout: int = 40) -> str | None:
    """Ask Groq/HF to write ONLY the function body for this tool from user text."""
    try:
        from ...chat_ai import groq_provider as groq
        from ...chat_ai import hf_provider as hf
    except Exception:
        return None

    providers = []
    if groq.enabled():
        providers.append(("groq", groq))
    if hf.enabled():
        providers.append(("hf", hf))
    if not providers:
        return None

    system = (
        "You write ONE Python function body for a Telegram bot tool. "
        "Output ONLY the function body (indented with 4 spaces), no markdown, no explanation. "
        "Signature in mind: def tool_NAME(target: str = '') -> dict\n"
        "Rules:\n"
        "- Use only the stdlib (re, json, urllib.request, socket, ssl, hashlib, datetime, math).\n"
        "- No eval/exec/subprocess/os.system/pickle/ctypes.\n"
        "- No hardcoded API keys or secrets.\n"
        "- Return a dict with ok:bool and relevant fields.\n"
        "- Implement what THIS user description asks for this specific action only.\n"
        "- If the description is vague, return a structured record of the input.\n"
        "- Do not invent unrelated features."
    )
    user = (
        f"TOOL_ID: {tid}\n"
        f"TOOL_TITLE: {title}\n"
        f"USER_BOT_DESCRIPTION:\n{(user_text or '')[:6000]}\n\n"
        f"Write the body of def tool_{tid}(target: str = '') -> dict:"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    max_tokens = int(os.environ.get("TOOL_EMIT_MAX_TOKENS", "1200"))
    for name, prov in providers:
        try:
            content, _model = prov.chat(
                messages,
                timeout=timeout,
                max_tokens=max_tokens,
                temperature=0.1,
            )
            body = _extract_function_body(content or "", tid)
            if body:
                return body
        except Exception as exc:
            logger.warning("dynamic tool gen failed %s %s: %s", name, tid, exc)
    return None


def emit_tools_module(inf: InferenceResult) -> str:
    tools = _collect_tools(inf)
    source = (getattr(inf, "source_text", None) or "").strip()
    use_ai = os.environ.get("DYNAMIC_TOOLS", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }

    if not tools:
        return (
            '"""No tools in this contract."""\n'
            "from __future__ import annotations\n\n"
            "TOOL_IDS: list[str] = []\n\n"
            "def run_tool(tool_id: str, target: str = \"\") -> str:\n"
            "    return \"لا توجد أدوات في مواصفات هذا البوت.\"\n"
        )

    lines: list[str] = [
        '"""Tools generated dynamically for this bot contract only."""',
        "from __future__ import annotations",
        "",
        "import hashlib",
        "import json",
        "import math",
        "import re",
        "import socket",
        "import ssl",
        "import urllib.request",
        "from datetime import datetime, timezone",
        "from typing import Any",
        "",
    ]

    tool_ids: list[str] = []
    for t in tools:
        tid = _safe_ident(str(t.get("id") or "tool"))
        if tid in tool_ids:
            continue
        tool_ids.append(tid)
        title = str(t.get("title") or tid)[:120]
        body = None
        if use_ai and source:
            body = _ai_generate_body(tid, title, source)
        if not body:
            body = _stub_body(tid)
        lines.append(f"def tool_{tid}(target: str = '') -> dict[str, Any]:")
        lines.append(f"    \"\"\"Dynamic tool from user contract: {title}\"\"\"")
        # body already indented
        lines.append(body.rstrip("\n"))
        lines.append("")

    lines += [
        f"TOOL_IDS: list[str] = {tool_ids!r}",
        "",
        "def run_tool(tool_id: str, target: str = '') -> str:",
        "    tid = re.sub(r'[^a-z0-9_]', '_', (tool_id or '').strip().lower()).strip('_')",
        "    fn = globals().get('tool_' + tid)",
        "    if not callable(fn):",
        "        return 'أداة غير موجودة في عقد هذا البوت: ' + tid",
        "    try:",
        "        r = fn(target)",
        "    except Exception as exc:",
        "        return 'خطأ: ' + str(exc)",
        "    if not isinstance(r, dict):",
        "        return str(r)[:3500]",
        "    if not r.get('ok', True):",
        "        return 'فشل: ' + str(r.get('error') or r)[:3500]",
        "    body = {k: v for k, v in r.items() if k != 'ok'}",
        "    return (tid + ': ' + str(body))[:3500]",
        "",
    ]
    return "\n".join(lines) + "\n"
