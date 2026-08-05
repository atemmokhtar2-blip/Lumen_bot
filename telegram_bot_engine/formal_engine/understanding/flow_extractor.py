"""
Extract workflow steps from long natural-language specs.
Supports linear AND branched flows (conditionals / choices).
Deterministic patterns only — no domain templates.
"""

from __future__ import annotations

import re
from typing import Any


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


def _detect_branch_points(steps: list[str]) -> dict[int, list[tuple[str, str]]]:
    """
    Detect choice/branch points inside step labels.
    Returns {step_index: [(choice_label, branch_hint), ...]}.
    """
    branches: dict[int, list[tuple[str, str]]] = {}
    choice_pat = re.compile(
        r"(?:إذا|لو)\s+(?:اختار|اختار المستخدم|اختار ال(?:مستخدم|عميل)|press|choose|select)?\s*"
        r"[«\"']?([^»\"'\n،,]{2,40})[»\"']?"
        r".{0,40}?"
        r"(?:ثم|بعدها|يطلب|يعرض|يقوم|goes? to|then)\s+([^\n.]{3,80})",
        re.I,
    )
    or_pat = re.compile(
        r"(?:أو|or)\s+[«\"']?([^»\"'\n،,]{2,40})[»\"']?",
        re.I,
    )
    for i, step in enumerate(steps):
        found: list[tuple[str, str]] = []
        for m in choice_pat.finditer(step):
            label = m.group(1).strip()
            hint = m.group(2).strip()
            if label and hint:
                found.append((label, hint))
        # also split "قالب متجر أو قالب مساعد"
        if not found and ("أو" in step or " or " in step.lower()):
            parts = re.split(r"\s+أو\s+|\s+or\s+", step, flags=re.I)
            if len(parts) >= 2:
                for p in parts:
                    p = p.strip()
                    if 2 < len(p) < 50:
                        found.append((p[:40], p[:60]))
        if found:
            branches[i] = found[:6]
    return branches


def steps_to_flow_units(steps: list[str], flow_name: str = "main") -> list[dict]:
    """
    Convert free-text steps into flow units.
    Supports branching: when a step has choices, emits a choice node
    with branches list instead of a single next_id.
    """
    if not steps:
        return []

    branch_map = _detect_branch_points(steps)
    units: list[dict] = []
    # pre-allocate ids
    ids = [f"s{i+1}" for i in range(len(steps))]

    for i, step in enumerate(steps):
        sid = ids[i]
        action = re.sub(r"\s+", "_", step.lower())
        action = re.sub(r"[^\w]+", "_", action, flags=re.UNICODE)[:48].strip("_") or sid
        next_id = ids[i + 1] if i + 1 < len(steps) else None

        unit: dict[str, Any] = {
            "id": sid,
            "action": action,
            "next_id": next_id,
            "label": step[:120],
        }

        if i in branch_map:
            choices = branch_map[i]
            branches = []
            for bi, (label, hint) in enumerate(choices):
                # each branch gets a synthetic follow-up id if we can map it
                # otherwise points to next linear step
                branch_id = f"{sid}_b{bi+1}"
                branches.append(
                    {
                        "label": label[:60],
                        "hint": hint[:80],
                        "next_id": next_id,  # default fall-through; codegen can specialize
                        "branch_id": branch_id,
                    }
                )
            unit["branches"] = branches
            unit["action"] = "choice" if "choice" not in action else action
            # choice nodes still advance linearly by default; branches carry alternatives
        units.append(unit)
    return units


def extract_flows(text: str) -> list[tuple[str, list[dict]]]:
    """
    Returns list of (flow_name, steps_dicts).
    Prefer workflow-like sections; else numbered + conditional steps from full text.
    Produces branched units when conditionals/choices are detected.
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
        for s in extract_conditional_steps(body):
            if s not in steps:
                steps.append(s)
    if not steps:
        steps = extract_conditional_steps(text)
    if not steps:
        return []
    return [("main", steps_to_flow_units(steps, "main"))]
