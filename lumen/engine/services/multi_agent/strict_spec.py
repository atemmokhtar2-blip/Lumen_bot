"""StrictSpec contract — machine-readable plan for the Builder (no chat fluff)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

STRICT_SPEC_SCHEMA = "strict_spec.v1"


@dataclass
class StrictSpec:
    schema: str = STRICT_SPEC_SCHEMA
    purpose: str = ""
    domain: str = ""
    features: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    language: str = "ar"
    spec_request: str = ""
    confidence: float = 0.0
    source: str = ""  # gemini | bridge | deterministic
    model: str = ""
    clarification_needed: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def is_buildable(self) -> bool:
        if self.clarification_needed:
            return False
        text = (self.spec_request or self.purpose or "").strip()
        if len(text) < 8:
            return False
        # Must look like a bot build request for generation
        low = text.lower()
        return any(k in low for k in ("بوت", "bot", "telegram")) or bool(self.features)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = max(0.0, min(1.0, float(self.confidence or 0.0)))
        d["features"] = list(self.features or [])[:80]
        d["flows"] = list(self.flows or [])[:40]
        d["commands"] = list(self.commands or [])[:40]
        d["entities"] = list(self.entities or [])[:40]
        d["constraints"] = list(self.constraints or [])[:40]
        d["spec_request"] = (self.spec_request or "")[:20000]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StrictSpec":
        d = dict(data or {})
        def slist(key: str) -> list[str]:
            v = d.get(key) or d.get("features_requested" if key == "features" else key) or []
            if not isinstance(v, list):
                return []
            return [str(x).strip() for x in v if str(x).strip()][:80]

        try:
            conf = float(d.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        return cls(
            schema=str(d.get("schema") or STRICT_SPEC_SCHEMA),
            purpose=str(d.get("purpose") or "").strip()[:500],
            domain=str(d.get("domain") or d.get("domain_hint") or "").strip()[:120],
            features=slist("features") or slist("features_requested"),
            flows=slist("flows"),
            commands=slist("commands"),
            entities=slist("entities"),
            constraints=slist("constraints"),
            language=str(d.get("language") or "ar")[:8],
            spec_request=str(d.get("spec_request") or "").strip()[:20000],
            confidence=max(0.0, min(1.0, conf)),
            source=str(d.get("source") or "").strip()[:40],
            model=str(d.get("model") or "").strip()[:80],
            clarification_needed=bool(d.get("clarification_needed")),
            clarification_questions=slist("clarification_questions")[:10],
            raw={k: v for k, v in d.items() if k not in {
                "schema", "purpose", "domain", "features", "features_requested", "flows",
                "commands", "entities", "constraints", "language", "spec_request",
                "confidence", "source", "model", "clarification_needed", "clarification_questions",
            }},
        )


def validate_strict_spec(spec: StrictSpec | dict[str, Any] | None) -> tuple[bool, list[str]]:
    if spec is None:
        return False, ["missing_spec"]
    s = spec if isinstance(spec, StrictSpec) else StrictSpec.from_dict(spec)
    errors: list[str] = []
    if s.schema != STRICT_SPEC_SCHEMA:
        errors.append("bad_schema")
    if not s.is_buildable():
        errors.append("not_buildable")
    if s.clarification_needed:
        errors.append("clarification_needed")
    return (len(errors) == 0, errors)


def merge_spec_request(spec: StrictSpec) -> str:
    """Produce a single deterministic request string for Cline generation."""
    if (spec.spec_request or "").strip():
        return spec.spec_request.strip()[:20000]
    parts = []
    if spec.purpose:
        parts.append(spec.purpose)
    if spec.features:
        parts.append("الميزات: " + ", ".join(spec.features[:30]))
    if spec.flows:
        parts.append("التدفقات: " + ", ".join(spec.flows[:15]))
    if spec.commands:
        parts.append("الأوامر: " + ", ".join(spec.commands[:20]))
    if spec.constraints:
        parts.append("قيود: " + ", ".join(spec.constraints[:15]))
    text = "\n".join(parts).strip()
    if text and "بوت" not in text and "bot" not in text.lower():
        text = "بوت تيليجرام: " + text
    return text[:20000]
