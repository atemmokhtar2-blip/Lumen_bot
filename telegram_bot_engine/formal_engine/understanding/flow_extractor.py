"""
Extract ordered workflow steps from long natural-language specs.
Pure deterministic patterns — no templates forcing a domain.
"""

from __future__ import annotations

import re
from typing import List, Tuple


def extract_numbered_steps(text: str) -> list[str]:
    """Return ordered step descriptions from 1. 2. or - bullets under workflow-like text."""
    steps: list[str] = []
    # Numbered: 1. ... 2) ... ١.
    for m in re.finditer(
        r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{5,160})",
        text,
    ):
        s = m.group(1).strip()
        if s and s not in steps:
            steps.append(s)
    if steps:
        return steps[:20]
    # Bullet lines that look like actions
    for m in re.finditer(r"(?:^|\n)\s*[\-•\*]\s*([^\n]{8,160})", text):
        s = m.group(1).strip()
        if any(k in s for k in ("ي", "user", "bot", "اضغط", "يعرض", " يطلب", "when", "then")):
            steps.append(s)
    return steps[:20]


def steps_to_flow_units(steps: list[str], flow_name: str = "main") -> list[dict]:
    """Convert free-text steps into {id, action, next_id} dicts for FlowUnit."""
    if not steps:
        return []
    units = []
    for i, step in enumerate(steps):
        sid = f"s{i+1}"
        action = re.sub(r"\s+", "_", step.lower())
        action = re.sub(r"[^\w]+", "_", action, flags=re.UNICODE)[:48].strip("_") or sid
        next_id = f"s{i+2}" if i + 1 < len(steps) else None
        units.append({"id": sid, "action": action, "next_id": next_id, "label": step[:120]})
    return units


def extract_flows(text: str) -> list[tuple[str, list[dict]]]:
    """
    Returns list of (flow_name, steps_dicts).
    Prefer section titled طريقة العمل / workflow; else whole text numbered steps.
    """
    section = ""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(k in s for k in ("طريقة العمل", "workflow", "how it works", "خطوات")) and len(s) < 40:
            start = i + 1
            break
    if start is not None:
        buf = []
        for line in lines[start:]:
            s = line.strip()
            if s and len(s) < 30 and any(k in s for k in ("الأوامر", "الأزرار", "الميزات", "commands", "buttons")):
                break
            buf.append(line)
        section = "\n".join(buf)
    body = section if section.strip() else text
    steps = extract_numbered_steps(body)
    if not steps:
        return []
    return [("main", steps_to_flow_units(steps, "main"))]
