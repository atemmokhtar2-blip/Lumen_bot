"""Pack lifecycle pipeline: Gap → ResearchSpec → Draft Pack → Validate → Register.

Never turns research text into executable code. Only structured packs.
"""
from __future__ import annotations

import re
from typing import Any

from ..gap_journal import GapRecord, list_open_gaps, mark_gap_status
from ..research_spec import ResearchSpec, research_spec_from_gap, save_research_spec
from .emit_contract import assess_pack_capabilities
from .loader import register_pack
from .schema import CapabilityPack, PackCapability, validate_pack


def _slug(text: str, *, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (text or "").lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "feature")[:max_len]


def draft_pack_from_research(
    spec: ResearchSpec,
    *,
    service: str = "generic",
    method: str = "echo",
    category: str = "general",
    actor: str = "user",
) -> CapabilityPack:
    """Build a draft pack from a ResearchSpec using a **known** emit pair by default.

    Default method=echo is intentionally safe (always emit-able). Authors must
    upgrade service/method to a known pair before production use.
    """
    key = _slug(spec.feature_id or spec.title)
    if not key.startswith("pack_"):
        key = f"pack_{key}"
    keywords = list(dict.fromkeys(
        list(spec.keywords or []) + [w for w in (spec.title or "").split() if len(w) > 2]
    ))[:16]
    cap = PackCapability(
        key=key,
        service=(service or "generic").lower(),
        method=(method or "echo").lower(),
        description_ar=spec.title or key,
        description_en=spec.summary or spec.title or key,
        category=category,
        default_actor=actor,
        keywords=keywords,
        dependencies=list(spec.dependencies or []),
    )
    return CapabilityPack(
        id=f"draft_{key}",
        version="0.1.0",
        name=spec.title or key,
        description=spec.summary or "",
        capabilities=[cap],
        source="gap_journal" if spec.source == "gap_journal" else "research",
        enabled=True,
    )


def draft_packs_from_open_gaps(*, limit: int = 10) -> list[dict[str, Any]]:
    """For each open gap: ResearchSpec + draft pack (not auto-registered)."""
    results: list[dict[str, Any]] = []
    for gap in list_open_gaps(limit=limit):
        rs = research_spec_from_gap(gap.phrase, gap.reason, request=gap.request_preview)
        save_research_spec(rs)
        pack = draft_pack_from_research(rs)
        errors = validate_pack(pack)
        assessments = [a.to_dict() for a in assess_pack_capabilities(pack.capabilities)]
        results.append({
            "gap": gap.to_dict(),
            "research_spec": rs.to_dict(),
            "draft_pack": pack.to_dict(),
            "validation_errors": errors,
            "emit_assessments": assessments,
        })
    return results


def approve_and_register(
    pack: CapabilityPack,
    *,
    require_safe_emit: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate + emit-assess + register. Blocks unsafe methods when require_safe_emit."""
    errors = validate_pack(pack)
    if errors:
        return {"ok": False, "errors": errors}
    assessments = assess_pack_capabilities(pack.capabilities)
    if require_safe_emit:
        unsafe = [a for a in assessments if not a.safe]
        if unsafe:
            return {
                "ok": False,
                "errors": [
                    f"{a.key}: {a.level} — {', '.join(a.notes)}" for a in unsafe
                ],
                "emit_assessments": [a.to_dict() for a in assessments],
            }
    result = register_pack(pack, overwrite=overwrite)
    result["emit_assessments"] = [a.to_dict() for a in assessments]
    return result


def resolve_gap_with_pack(
    phrase: str,
    reason: str,
    pack: CapabilityPack,
    *,
    require_safe_emit: bool = True,
) -> dict[str, Any]:
    """Register pack and mark matching gap resolved."""
    reg = approve_and_register(pack, require_safe_emit=require_safe_emit, overwrite=False)
    if not reg.get("ok"):
        return reg
    mark_gap_status(phrase, reason, "resolved")
    reg["gap_status"] = "resolved"
    return reg


__all__ = [
    "draft_pack_from_research",
    "draft_packs_from_open_gaps",
    "approve_and_register",
    "resolve_gap_with_pack",
]
