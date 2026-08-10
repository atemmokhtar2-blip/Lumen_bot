"""Dynamic composition layer on top of existing presets.

Enhances preset-stack sessions with capability extraction and multi-domain
hints — without inventing capabilities the emitter cannot implement.
"""
from __future__ import annotations

import re
from typing import Any

from .builder import BuilderSession
from .capability_extractor import extract_all
from .domain_detector import detect, detect_detailed, domains_to_presets
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
    """Main entry: multi-domain + extracted caps → real BotSpec."""
    domains = detect(text)
    domain_presets = domains_to_presets(domains)
    stack = detect_preset_stack(text, limit=6)

    # Prefer domain presets when they are more specific than weak commerce hits
    cyber_strong = "cybersecurity" in domains or "security_ops" in stack
    if cyber_strong:
        # Security-first stack: drop commerce noise unless user clearly asked shop
        stack = [p for p in stack if p not in {"commerce_pro", "shop"}]
        if "security_ops" not in stack:
            stack = ["security_ops"] + stack
        for p in domain_presets:
            if p not in stack:
                stack.append(p)
    else:
        for p in domain_presets:
            if p not in stack:
                stack.append(p)

    stack = stack[:6] or ["echo_basic"]
    session = compose_session(stack, user_id=user_id, request=text)

    # Inject extracted real capabilities
    extra_keys = extract_all(text, domains)
    for key in extra_keys:
        if key in CAPABILITIES:
            session.selected.add(key)

    # CyberGuard / security packs: ensure domain-check suite is present
    if cyber_strong:
        for key in (
            "sec_dns_check", "sec_mx_check", "sec_tls_check", "sec_http_check",
            "sec_headers_check", "sec_domain_overview", "sec_password_tips",
            "sec_report_phish", "sec_report_incident", "sec_checklist", "sec_tips",
            "sec_list_reports", "sec_close_report",
            "project_create", "project_list", "project_view",
            "report_create", "report_list",
            "note_add", "note_list", "task_add", "task_list",
            "start", "help", "lang", "my_id", "rules",
        ):
            if key in CAPABILITIES:
                session.selected.add(key)

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

    return session.to_spec()


def composition_debug(text: str) -> dict[str, Any]:
    """Inspect what the composer would select (for tests / ops)."""
    domains = detect_detailed(text)
    keys = extract_all(text, [d.domain for d in domains])
    stack = detect_preset_stack(text, limit=6)
    return {
        "domains": [{"domain": d.domain, "score": d.score, "matched": list(d.matched)} for d in domains],
        "extracted_keys": keys,
        "preset_stack": stack,
        "bot_name": extract_bot_name(text),
    }


__all__ = ["compose_from_text", "composition_debug", "extract_bot_name"]
