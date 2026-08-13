"""Dynamic composition layer on top of existing presets.

Enhances preset-stack sessions with capability extraction and multi-domain
hints — without inventing capabilities the emitter cannot implement.
"""
from __future__ import annotations

import re
from typing import Any

from .builder import BuilderSession
from .capability_extractor import extract_all
from .domain_detector import decide, detect_detailed, decision_to_presets
from .presets import compose_session, detect_preset_stack
from .registry import CAPABILITIES
from .schema import BotSpec


_NAME_PATTERNS = (
    re.compile(r"(?:اسمه|اسمها|يسمى|تسمى)\s+([A-Za-z0-9_\u0600-\u06FF]{2,40})", re.I),
    re.compile(r"(?:named|called|name(?:d)?)\s+([A-Za-z0-9_]{2,40})", re.I),
    re.compile(r"\b([A-Z][a-zA-Z0-9]{2,30}(?:Guard|Bot|Ops|Hub|Pro)?)\b"),
)


def extract_bot_name(text: str) -> str | None:
    for pat in _NAME_PATTERNS:
        m = pat.search(text or "")
        if m:
            name = m.group(1).strip().strip(".,;:!")
            if name.lower() not in {"bot", "telegram", "تيليجرام", "بوت"}:
                return name[:40]
    return None


def compose_from_text(text: str, *, user_id: int = 0) -> BotSpec:
    """Main entry: domain decision is authoritative, then presets + caps."""
    decision = decide(text)
    domains = list(decision.allowed_domains)
    domain_presets = decision_to_presets(decision)
    stack = detect_preset_stack(text, limit=6)

    # Domain-layer vetoes (Phase A root) — presets may not override these
    noise: set[str] = set(decision.blocked_presets)
    cyber_strong = "cybersecurity" in domains or "security_ops" in stack
    modern = {"iot", "blockchain", "ai_ml", "devops", "gaming", "healthcare", "education"}
    modern_hit = bool(modern & set(domains))
    if cyber_strong:
        noise |= {"commerce_pro", "shop"}
    if modern_hit:
        noise |= {"commerce_pro"}
        if "iot" in domains or "ai_ml" in domains or "gaming" in domains:
            noise |= {"saas"}
        if "healthcare" in domains:
            noise |= {"booking"}

    # Strong tasks primary → lock stack to tasks only (no booking/clinic bleed)
    if decision.primary in {"tasks", "projects"} and decision.confidence >= 0.45:
        stack = [p for p in domain_presets if p not in noise] or ["tasks"]
        stack = [stack[0]]  # single primary preset
    else:
        stack = [p for p in stack if p not in noise]
        ordered: list[str] = []
        for p in domain_presets + stack:
            if p not in ordered and p not in noise:
                ordered.append(p)
        stack = ordered[:6] or ["echo_basic"]

    session = compose_session(stack, user_id=user_id, request=text)

    # Extract caps only for allowed domains (never blocked vertical suites)
    extra_keys = extract_all(text, domains, decision=decision)
    for key in extra_keys:
        if key in CAPABILITIES:
            session.selected.add(key)

    # Domain-specific guaranteed suites (registry-backed only)
    # Phase C: domain suites come only from extract_all(..., decision=decision)
    # with text-evidence gates. Fat local _SUITE packs removed to stop inflation.

    name = extract_bot_name(text)
    if name:
        # Assign directly — BuilderSession.set_name re-runs arabic_intent extract
        # which may replace a clean proper noun with a domain id.
        cleaned = re.sub(r"[^A-Za-z0-9_\u0600-\u06FF\-]+", "_", name).strip("_")[:40]
        if cleaned:
            session.bot_name = cleaned
        hits = detect_detailed(text, limit=3)
        domain_str = " + ".join(h.domain for h in hits) if hits else "custom"
        session.set_description(f"{cleaned or name}: {domain_str} (dynamic compose)")

    # Arabic UI when Arabic script present
    if any("\u0600" <= ch <= "\u06FF" for ch in (text or "")):
        session.language = "ar"

        # Phase C root: resolve_capabilities is the single authority for selected set
    try:
        from .capability_extractor import resolve_capabilities
        resolved = resolve_capabilities(text, presets=list(stack), decision=decision)
        if resolved:
            session.selected = set(resolved)
    except Exception:
        pass

    return session.to_spec()



def composition_debug(text: str) -> dict[str, Any]:
    """Inspect what the composer would select (for tests / ops)."""
    decision = decide(text)
    keys = extract_all(text, list(decision.allowed_domains))
    stack = detect_preset_stack(text, limit=6)
    stack = [p for p in stack if p not in decision.blocked_presets]
    return {
        "decision": {
            "primary": decision.primary,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "blocked_presets": sorted(decision.blocked_presets),
            "allowed_domains": list(decision.allowed_domains),
        },
        "domains": [
            {"domain": d.domain, "score": d.score, "matched": list(d.matched)}
            for d in decision.hits
        ],
        "extracted_keys": keys,
        "preset_stack": stack,
        "bot_name": extract_bot_name(text),
    }


__all__ = ["compose_from_text", "composition_debug", "extract_bot_name"]
