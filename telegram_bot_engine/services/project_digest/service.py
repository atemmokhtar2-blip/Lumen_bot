"""
Build a compact, dynamic digest of a project directory for the AI chat layer.

Reads real files only — no canned bot descriptions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


_SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", "versions", ".tbe_venv"}


def _list_py(root: Path, limit: int = 40) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*.py")):
        if any(s in p.parts for s in _SKIP):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _extract_commands_from_source(text: str) -> list[str]:
    cmds: list[str] = []
    # CommandHandler("name" or 'name'
    for m in re.finditer(
        r'CommandHandler\s*\(\s*[\'"]([a-zA-Z][a-zA-Z0-9_]{0,40})[\'"]',
        text,
    ):
        cmds.append(m.group(1))
    # ROUTES / commands lists
    for m in re.finditer(
        r'[\'"]/?(start|help|[a-z][a-z0-9_]{1,30})[\'"]\s*:',
        text,
    ):
        cmds.append(m.group(1))
    # TOOL_IDS = ['a','b']
    m = re.search(r"TOOL_IDS\s*=\s*\[([^\]]+)\]", text)
    if m:
        cmds.extend(re.findall(r"[\'\"]([a-zA-Z][a-zA-Z0-9_]*)[\'\"]", m.group(1)))
    # FLOWS keys
    m = re.search(r"FLOWS\s*=\s*\{([^}]+)\}", text, re.S)
    if m:
        cmds.extend(re.findall(r"[\'\"]([a-zA-Z][a-zA-Z0-9_]*)[\'\"]\s*:", m.group(1)))
    # dedupe preserve order
    seen = set()
    out = []
    for c in cmds:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:40]


def _extract_flows_snippet(text: str) -> str:
    m = re.search(r"FLOWS\s*:\s*dict[^=]*=\s*(\{.*?\n\})", text, re.S)
    if not m:
        m = re.search(r"FLOWS\s*=\s*(\{.*?\n\})", text, re.S)
    if not m:
        return ""
    snippet = m.group(1)
    return snippet[:800]


def build_project_digest(project_path: str | Path, *, source_request: str = "") -> dict[str, Any]:
    root = Path(project_path).resolve()
    digest: dict[str, Any] = {
        "path": str(root),
        "exists": root.is_dir(),
        "files": [],
        "commands": [],
        "flows_preview": "",
        "entry_points": [],
        "source_request_preview": (source_request or "")[:300],
        "ai_context": "",
    }
    if not root.is_dir():
        return digest

    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(s in p.parts for s in _SKIP):
            continue
        try:
            rel = str(p.relative_to(root))
        except Exception:
            rel = p.name
        files.append(rel)
        if len(files) >= 50:
            break
    digest["files"] = files

    all_cmds: list[str] = []
    flows_preview = ""
    for py in _list_py(root):
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        all_cmds.extend(_extract_commands_from_source(text))
        if not flows_preview and "FLOWS" in text:
            flows_preview = _extract_flows_snippet(text)
        if py.name in ("main.py", "bot.py", "app.py"):
            digest["entry_points"].append(str(py.relative_to(root)))

    seen = set()
    cmds = []
    for c in all_cmds:
        if c not in seen:
            seen.add(c)
            cmds.append(c)
    digest["commands"] = cmds
    digest["flows_preview"] = flows_preview

    parts = [
        f"active_project_path={root}",
        f"files={', '.join(files[:30])}",
        f"commands={', '.join('/'+c for c in cmds)}" if cmds else "commands=",
    ]
    if digest["entry_points"]:
        parts.append("entry=" + ", ".join(digest["entry_points"]))
    if source_request:
        parts.append("original_user_request=" + source_request[:250])
    if flows_preview:
        parts.append("flows_structure=\n" + flows_preview[:600])
    digest["ai_context"] = "\n".join(parts)[:3500]
    return digest


__all__ = ["build_project_digest"]
