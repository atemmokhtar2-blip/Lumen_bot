"""
tools.py — generated only from this request's contract tool/command ids.

ZERO saved domain packs. ZERO primitive tables (no DNS/SPF/HTTP catalogs).
Each tool is a pure function: action name + user input → structured record.
"""
from __future__ import annotations

import re
from typing import Any

from ..inference.engine import InferenceResult


def _safe_ident(tid: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (tid or "").strip().lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "tool_" + (s or "x")
    return s[:48]


def emit_tools_module(inf: InferenceResult) -> str:
    tools = [t for t in (getattr(inf, "dynamic_tools", None) or []) if isinstance(t, dict)]
    seen: set[str] = {str(t.get("id") or "").lower() for t in tools}
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

    if not tools:
        return (
            '"""No tools in this contract."""\n'
            "from __future__ import annotations\n\n"
            "TOOL_IDS: list[str] = []\n\n"
            "def run_tool(tool_id: str, target: str = \"\") -> str:\n"
            "    return \"لا توجد أدوات في مواصفات هذا البوت.\"\n"
        )

    lines: list[str] = [
        '"""Tools bound only to this bot contract — no saved domain packs."""',
        "from __future__ import annotations",
        "",
        "import re",
        "from typing import Any",
        "",
    ]

    tool_ids: list[str] = []
    for t in tools:
        tid = _safe_ident(str(t.get("id") or "tool"))
        if tid in tool_ids:
            continue
        tool_ids.append(tid)
        title = str(t.get("title") or tid)[:80]
        lines.append(f"def tool_{tid}(target: str = '') -> dict[str, Any]:")
        lines.append(f"    \"\"\"Contract tool: {title}\"\"\"")
        lines.append(f"    return {{'ok': True, 'action': {tid!r}, 'input': (target or '')[:2000]}}")
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
