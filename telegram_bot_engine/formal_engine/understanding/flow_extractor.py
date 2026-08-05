"""
Extract ordered workflow steps from long natural-language specs.
Deterministic patterns only — no domain templates.
"""

from __future__ import annotations

import re
from typing import List, Tuple


def extract_numbered_steps(text: str) -> list[str]:
    """Return ordered step descriptions from numbered or action-like lines."""
    steps: list[str] = []
    seen: set[str] = set()

    def _push(s: str) -> None:
        s = re.sub(r"\s+", " ", (s or "").strip())
        if 5 <= len(s) <= 160 and s not in seen:
            seen.add(s)
            steps.append(s)

    for m in re.finditer(
        r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{5,160})",
        text,
    ):
        _push(m.group(1))
    if steps:
        return steps[:25]

    for m in re.finditer(r"(?:^|\n)\s*[\-•\*]\s*([^\n]{8,160})", text):
        s = m.group(1).strip()
        if any(
            k in s
            for k in (
                "ي",
                "user",
                "bot",
                "اضغط",
                "يعرض",
                "يطلب",
                "when",
                "then",
                "إذا",
                "ثم",
                "يقوم",
            )
        ):
            _push(s)
    return steps[:25]


def extract_conditional_steps(text: str) -> list[str]:
    """إذا/لو … ثم/بعدها chains as ordered steps."""
    steps: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"((?:إذا|لو)\s+[^\n.]{5,120})", text):
        s = m.group(1).strip()
        if s not in seen:
            seen.add(s)
            steps.append(s)
    for m in re.finditer(r"((?:ثم|بعدها|بعد ذلك)\s+[^\n.]{5,120})", text):
        s = m.group(1).strip()
        if s not in seen:
            seen.add(s)
            steps.append(s)
    return steps[:20]


def steps_to_flow_units(steps: list[str], flow_name: str = "main") -> list[dict]:
    """Convert free-text steps into {id, action, next_id, label} for FlowUnit."""
    if not steps:
        return []
    units = []
    for i, step in enumerate(steps):
        sid = f"s{i+1}"
        action = re.sub(r"\s+", "_", step.lower())
        action = re.sub(r"[^\w]+", "_", action, flags=re.UNICODE)[:48].strip("_") or sid
        next_id = f"s{i+2}" if i + 1 < len(steps) else None
        units.append(
            {
                "id": sid,
                "action": action,
                "next_id": next_id,
                "label": step[:120],
            }
        )
    return units


def extract_flows(text: str) -> list[tuple[str, list[dict]]]:
    """
    Returns list of (flow_name, steps_dicts).
    Prefer workflow-like sections; else numbered + conditional steps from full text.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(
            k in s
            for k in (
                "طريقة العمل",
                "workflow",
                "how it works",
                "خطوات",
                "السيناريو",
                "سيناريو",
            )
        ) and len(s) < 48:
            start = i + 1
            break
    section = ""
    if start is not None:
        buf = []
        for line in lines[start:]:
            s = line.strip()
            if s and len(s) < 30 and any(
                k in s
                for k in (
                    "الأوامر",
                    "الأزرار",
                    "الميزات",
                    "commands",
                    "buttons",
                    "الأدوار",
                )
            ):
                break
            buf.append(line)
        section = "\n".join(buf)

    body = section if section.strip() else text
    steps = extract_numbered_steps(body)
    if len(steps) < 2:
        # merge conditionals
        for s in extract_conditional_steps(body):
            if s not in steps:
                steps.append(s)
    if not steps:
        steps = extract_conditional_steps(text)
    if not steps:
        return []
    return [("main", steps_to_flow_units(steps, "main"))]
