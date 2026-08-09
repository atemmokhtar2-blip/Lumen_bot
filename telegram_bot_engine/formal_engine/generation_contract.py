"""
Generation contract gate — world-class quality without domain templates.

Assesses whether the grounded user/AI text carries enough *evidenced*
structure to justify running the formal codegen. Refuses hollow bots
that would only emit /start+/help.

Everything is derived from extract_dsl on the actual text — no saved packs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContractAssessment:
    ready: bool
    score: float = 0.0
    command_names: list[str] = field(default_factory=list)
    meaningful_commands: list[str] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    entity_fields: dict[str, list[str]] = field(default_factory=dict)
    button_labels: list[str] = field(default_factory=list)
    flow_hints: int = 0
    gaps: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "score": self.score,
            "command_names": list(self.command_names),
            "meaningful_commands": list(self.meaningful_commands),
            "entity_names": list(self.entity_names),
            "entity_fields": {k: list(v) for k, v in self.entity_fields.items()},
            "button_labels": list(self.button_labels),
            "flow_hints": self.flow_hints,
            "gaps": list(self.gaps),
            "evidence": dict(self.evidence),
        }

    def to_ai_context(self) -> str:
        """Compact dynamic brief for SmartChat — not a user-facing script."""
        parts = [
            f"contract_ready={self.ready}",
            f"score={self.score:.2f}",
            f"commands={','.join(self.command_names)}",
            f"meaningful={','.join(self.meaningful_commands)}",
            f"entities={','.join(self.entity_names)}",
            f"buttons={','.join(self.button_labels[:12])}",
            f"flow_hints={self.flow_hints}",
        ]
        if self.gaps:
            parts.append("gaps=" + ",".join(self.gaps))
        if self.entity_fields:
            ef = "; ".join(f"{k}:{','.join(v)}" for k, v in list(self.entity_fields.items())[:8])
            parts.append("fields=" + ef)
        return "\n".join(parts)


def assess_generation_contract(text: str) -> ContractAssessment:
    """
    Run pure DSL extraction on text and score structural richness.
    No domain dictionaries — only structure present in the text.
    """
    from .dsl.extractor import extract_dsl

    raw = (text or "").strip()
    a = ContractAssessment(ready=False)
    if not raw:
        a.gaps.append("empty_text")
        return a

    try:
        prog = extract_dsl(raw)
    except Exception as exc:
        a.gaps.append(f"parse_error:{type(exc).__name__}")
        a.evidence["parse_error"] = str(exc)[:200]
        return a

    cmds = [c.name for c in (prog.commands or []) if getattr(c, "name", None)]
    a.command_names = cmds
    a.meaningful_commands = [n for n in cmds if n not in ("start", "help")]

    ents = list(prog.entities or [])
    a.entity_names = [e.name for e in ents if getattr(e, "name", None)]
    for e in ents:
        attrs = list(getattr(e, "attributes", None) or [])
        if attrs:
            a.entity_fields[e.name] = attrs

    btns = list(getattr(prog, "buttons", None) or [])
    a.button_labels = [
        (getattr(b, "label", None) or getattr(b, "name", None) or str(b))[:40]
        for b in btns
    ]

    ops = list(getattr(prog, "operations", None) or [])
    rules = list(getattr(prog, "rules", None) or [])
    a.flow_hints = len(ops) + sum(
        1
        for c in (prog.commands or [])
        if any(
            k in (getattr(c, "description", None) or "").lower()
            for k in ("جمع", "يجمع", "اجمع", "يطلب", "collect", "ask", "(", "حقل")
        )
    )

    score = 0.0
    score += min(0.55, 0.18 * len(a.meaningful_commands))
    score += min(0.20, 0.07 * len(a.entity_names))
    score += min(0.12, 0.03 * sum(len(v) for v in a.entity_fields.values()))
    score += min(0.10, 0.04 * len(a.button_labels))
    score += min(0.10, 0.03 * a.flow_hints)
    if len(raw) >= 100:
        score += 0.05
    if len(raw) >= 220:
        score += 0.05
    a.score = min(1.0, score)

    if not a.meaningful_commands:
        a.gaps.append("no_meaningful_commands")
    if a.meaningful_commands and not a.entity_fields and a.flow_hints == 0:
        # collect-style commands without fields — soft gap, still may be ready
        collectish = [
            n
            for n, c in (
                (getattr(c, "name", ""), c) for c in (prog.commands or [])
            )
            if n in a.meaningful_commands
            and any(
                k in (getattr(c, "description", None) or "")
                for k in ("جمع", "يجمع", "يطلب", "collect")
            )
        ]
        if collectish:
            a.gaps.append("collect_without_fields")

    # Ready: at least one real command beyond structural minima, or rich entities+buttons
    a.ready = bool(
        len(a.meaningful_commands) >= 1
        or (len(a.entity_names) >= 1 and len(a.button_labels) >= 1)
        or (len(a.meaningful_commands) >= 1 and a.score >= 0.25)
    )
    # Hollow: only start/help
    if not a.meaningful_commands and not a.entity_names and not a.button_labels:
        a.ready = False
        if "no_meaningful_commands" not in a.gaps:
            a.gaps.append("hollow_surface")

    a.evidence = {
        "ops": len(ops),
        "rules": len(rules),
        "text_len": len(raw),
    }
    return a


__all__ = ["ContractAssessment", "assess_generation_contract"]
