"""
UnderstandingService — Formal DSL extraction only.
No archetype packs, no domain templates, no behavior emission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnderstandingResult:
    ok: bool = True
    engine_path: str = "dsl_formal"
    entities: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    relations: int = 0
    operations: int = 0
    rules: int = 0
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "engine_path": self.engine_path,
            "entities": list(self.entities),
            "commands": list(self.commands),
            "buttons": list(self.buttons),
            "relations": self.relations,
            "operations": self.operations,
            "rules": self.rules,
            "actions": list(self.actions),
            "errors": list(self.errors),
        }


class UnderstandingService:
    """text → Custom DSL → Inference (no templates)."""

    def run(self, user_text: str) -> UnderstandingResult:
        try:
            from ...dsl.extractor import extract_dsl
            from ...inference.engine import infer

            program = extract_dsl(user_text or "")
            inf = infer(program)
        except Exception as exc:
            return UnderstandingResult(ok=False, errors=[f"{type(exc).__name__}: {exc}"])

        return UnderstandingResult(
            ok=True,
            engine_path="dsl_formal",
            entities=[e.name for e in program.entities],
            commands=[c.name for c in program.commands],
            buttons=[b.label for b in program.buttons],
            relations=len(program.relations),
            operations=len(program.operations),
            rules=len(getattr(program, "rules", []) or []),
            actions=list(inf.actions),
            raw={
                "source_hash": program.source_hash,
                "loops": [l.name for l in inf.loops],
                "decisions": [d.name for d in inf.decisions],
                "schemas": [s.table for s in inf.schemas],
            },
        )


def understand(user_text: str) -> UnderstandingResult:
    return UnderstandingService().run(user_text)
