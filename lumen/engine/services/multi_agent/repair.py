"""Phase C repair directives — structured QA → Architect instructions (fail-closed)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .state import AgentState
from .strict_spec import StrictSpec, merge_spec_request


@dataclass
class RepairDirective:
    """Machine-readable repair plan derived from qa_report."""
    attempt: int = 0
    blocking_errors: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    # Spec mutations suggested by rules
    drop_features: list[str] = field(default_factory=list)
    add_constraints: list[str] = field(default_factory=list)
    force_spec_prefix: str = ""
    previous_spec_hash: str = ""
    stagnant: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_prompt_block(self) -> str:
        lines = [
            f"REPAIR_ATTEMPT={self.attempt}",
            "BLOCKING_ERRORS:",
            *[f"- {e}" for e in self.blocking_errors[:15]],
            "REQUIRED_ACTIONS:",
            *[f"- {a}" for a in self.actions[:15]],
        ]
        if self.add_constraints:
            lines.append("ADD_CONSTRAINTS:")
            lines.extend(f"- {c}" for c in self.add_constraints[:10])
        if self.drop_features:
            lines.append("DROP_FEATURES:")
            lines.extend(f"- {f}" for f in self.drop_features[:10])
        return "\n".join(lines)


def spec_hash(spec: dict[str, Any] | StrictSpec | None) -> str:
    if spec is None:
        return ""
    d = spec.to_dict() if isinstance(spec, StrictSpec) else dict(spec or {})
    payload = {
        "purpose": d.get("purpose"),
        "features": d.get("features") or d.get("features_requested"),
        "spec_request": d.get("spec_request"),
        "constraints": d.get("constraints"),
    }
    raw = repr(payload).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:16]


def build_repair_directive(state: AgentState) -> RepairDirective:
    rep = state.qa_report or {}
    errors = [str(e) for e in (rep.get("errors") or []) if str(e).strip()]
    warnings = [str(w) for w in (rep.get("warnings") or []) if str(w).strip()]
    details = rep.get("details") if isinstance(rep.get("details"), dict) else {}

    actions: list[str] = []
    # Phase A+: prefer structured findings → precise worker actions
    try:
        from .findings import CritiqueFinding, findings_to_repair_actions
        raw_f = list((state.extensions or {}).get("findings") or [])
        findings = [CritiqueFinding.from_dict(x) for x in raw_f if isinstance(x, dict)]
        actions.extend(findings_to_repair_actions(findings))
    except Exception:
        pass
    drop: list[str] = []
    constraints: list[str] = []
    prefix_bits: list[str] = []

    joined = " ".join(errors).lower()

    # Rule library: map error patterns → concrete repair actions
    if any(k in joined for k in ("stub", "handler", "commandhandler", "command_bind")):
        actions.append("ensure every registered command has a non-stub async handler body")
        constraints.append("لا handlers فارغة أو stub")
        prefix_bits.append("يجب تنفيذ handlers حقيقية لكل أمر")
    if any(k in joined for k in ("syntax", "ast", "indent", "parse")):
        actions.append("regenerate with valid Python syntax; avoid incomplete blocks")
        constraints.append("كود بايثون صالح نحوياً")
    if any(k in joined for k in ("import", "module", "no module")):
        actions.append("fix imports and requirements.txt for used modules only")
        constraints.append("imports متسقة مع requirements")
    if any(k in joined for k in ("main.py", "entry", "entrypoint")):
        actions.append("ensure main.py entrypoint exists and starts the bot")
        constraints.append("وجود main.py قابل للتشغيل")
    if any(k in joined for k in ("message_handler", "msgs", "conversation")):
        actions.append("wire MessageHandler and conversation flows for text states")
        constraints.append("MessageHandler للتدفقات الحوارية")
    if any(k in joined for k in ("empty", "no_generated", "build_failed", "spec_gate")):
        actions.append("simplify strict_spec to core features only and strengthen spec_request")
        constraints.append("تبسيط الميزات للنواة فقط")
    if any(k in joined for k in ("static_dev_gate", "fidelity")):
        actions.append("align generated structure with static gate rules (handlers, cmds, flows)")
        constraints.append("الالتزام بقواعد static_dev_gate")

    # gen_verify stub_handlers detail
    gv = details.get("gen_verify") if isinstance(details, dict) else None
    if isinstance(gv, dict):
        stubs = gv.get("stub_handlers") or []
        if stubs:
            actions.append(f"implement real bodies for handlers: {', '.join(str(s) for s in stubs[:8])}")
            constraints.append("إصلاح stub handlers: " + ", ".join(str(s) for s in stubs[:5]))

    if not actions:
        actions.append("revise strict_spec and spec_request to address QA errors explicitly")
        constraints.append("معالجة أخطاء QA صراحة في المواصفات")

    # Align with verified-fallback budget (default 1): trim excess features early.
    attempt = int(state.attempts or 0)
    spec = StrictSpec.from_dict(state.strict_spec or {})
    if attempt >= 1 and len(spec.features) > 4:
        drop = list(spec.features[4:])
        actions.append("reduce features to the first 4 core capabilities")
        constraints.append("قلّل الميزات إلى 4 كحد أقصى")

    prev = ""
    hist = (state.extensions or {}).get("repair_history") or []
    if hist:
        prev = str((hist[-1] or {}).get("spec_hash") or "")

    return RepairDirective(
        attempt=attempt,
        blocking_errors=errors[:20],
        soft_warnings=warnings[:15],
        actions=actions[:15],
        drop_features=drop,
        add_constraints=constraints[:12],
        force_spec_prefix=" | ".join(prefix_bits)[:400],
        previous_spec_hash=prev,
    )


def apply_deterministic_repair(spec: StrictSpec, directive: RepairDirective) -> StrictSpec:
    """Mutate StrictSpec using directive — always changes something when errors exist."""
    features = [f for f in (spec.features or []) if f not in set(directive.drop_features or [])]
    if directive.drop_features and len(features) > 4:
        features = features[:4]
    constraints = list(spec.constraints or [])
    for c in directive.add_constraints:
        if c not in constraints:
            constraints.append(c)
    # Strengthen spec_request
    base = (spec.spec_request or merge_spec_request(spec) or "").strip()
    repair_note = ""
    if directive.blocking_errors:
        repair_note = (
            "\n\n[إصلاح QA]\n"
            + "\n".join(f"- {e}" for e in directive.blocking_errors[:8])
            + "\n[إجراءات مطلوبة]\n"
            + "\n".join(f"- {a}" for a in directive.actions[:8])
        )
    if directive.force_spec_prefix:
        base = f"{directive.force_spec_prefix}\n{base}"
    new_req = (base + repair_note).strip()[:20000]
    if not new_req:
        new_req = "بوت تيليجرام بسيط مع /start و /help"
    # Ensure change vs previous
    if directive.previous_spec_hash and spec_hash({
        "purpose": spec.purpose,
        "features": features,
        "spec_request": new_req,
        "constraints": constraints,
    }) == directive.previous_spec_hash:
        new_req = (new_req + f"\n# repair_nonce={directive.attempt}").strip()[:20000]

    return StrictSpec(
        schema=spec.schema,
        purpose=spec.purpose or "بوت مُصلَح بعد QA",
        domain=spec.domain,
        features=features,
        flows=list(spec.flows or []),
        commands=list(spec.commands or []),
        entities=list(spec.entities or []),
        constraints=constraints,
        language=spec.language or "ar",
        spec_request=new_req,
        confidence=min(0.85, max(0.4, float(spec.confidence or 0.5))),
        source=f"{spec.source}+repair" if spec.source else "repair",
        model=spec.model,
        clarification_needed=False,
        clarification_questions=[],
        raw={**(spec.raw or {}), "repair": directive.to_dict()},
    )


def record_repair_history(state: AgentState, directive: RepairDirective, new_hash: str) -> None:
    hist = list((state.extensions or {}).get("repair_history") or [])
    hist.append({
        "attempt": directive.attempt,
        "spec_hash": new_hash,
        "errors": list(directive.blocking_errors)[:10],
        "actions": list(directive.actions)[:10],
    })
    state.extensions["repair_history"] = hist[-10:]
    state.extensions["last_repair"] = directive.to_dict()
