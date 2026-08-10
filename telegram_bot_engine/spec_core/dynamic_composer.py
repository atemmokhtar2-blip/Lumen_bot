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

    cyber_strong = "cybersecurity" in domains or "security_ops" in stack
    modern = {"iot", "blockchain", "ai_ml", "devops", "gaming", "healthcare", "education"}
    modern_hit = bool(modern & set(domains))

    noise: set[str] = set()
    if cyber_strong:
        noise |= {"commerce_pro", "shop"}
    if modern_hit:
        noise |= {"commerce_pro"}
        if "iot" in domains or "ai_ml" in domains or "gaming" in domains:
            noise |= {"saas"}
        if "healthcare" in domains:
            noise |= {"booking"}  # clinic preset is more precise

    stack = [p for p in stack if p not in noise]
    # Domain presets lead the stack
    ordered: list[str] = []
    for p in domain_presets + stack:
        if p not in ordered and p not in noise:
            ordered.append(p)
    stack = ordered[:6] or ["echo_basic"]
    session = compose_session(stack, user_id=user_id, request=text)

    # Inject extracted real capabilities
    extra_keys = extract_all(text, domains)
    for key in extra_keys:
        if key in CAPABILITIES:
            session.selected.add(key)

    # Domain-specific guaranteed suites (registry-backed only)
    _SUITE: dict[str, tuple[str, ...]] = {
        "cybersecurity": (
            "sec_dns_check", "sec_mx_check", "sec_tls_check", "sec_http_check",
            "sec_headers_check", "sec_domain_overview", "sec_password_tips",
            "sec_report_phish", "sec_report_incident", "sec_checklist", "sec_tips",
            "sec_list_reports", "sec_close_report",
            "project_create", "project_list", "project_view",
            "report_create", "report_list",
            "note_add", "note_list", "task_add", "task_list",
            "start", "help", "lang", "my_id", "rules",
        ),
        "iot": (
            "device_list", "device_create", "device_view", "device_search",
            "sensor_list", "sensor_create", "sensor_view", "sensor_search",
            "note_add", "note_list", "task_add", "task_list", "start", "help", "lang",
        ),
        "blockchain": (
            "wallet_balance", "wallet_history", "wallet_transfer", "wallet_topup",
            "note_add", "ticket_open", "start", "help", "lang",
        ),
        "ai_ml": (
            "note_add", "note_list", "task_add", "task_list",
            "project_create", "project_list", "start", "help", "lang",
        ),
        "devops": (
            "deploy_list", "deploy_create", "deploy_view", "deploy_search",
            "env_list", "secret_list", "log_list",
            "task_add", "task_list", "note_add", "start", "help", "lang",
        ),
        "gaming": (
            "leaderboard", "contests", "join_contest", "balance",
            "achievement_list", "points_history", "start", "help", "lang",
        ),
        "healthcare": (
            "clinic_book", "clinic_my", "clinic_cancel", "clinic_slots",
            "patient_list", "patient_create", "doctor2_list",
            "prescription_list", "start", "help", "lang",
        ),
        "education": (
            "course_list", "course_enroll", "lesson_list", "lesson_open",
            "quiz_start", "quiz_score", "homework_submit", "start", "help", "lang",
        ),
    }
    for d in domains:
        for key in _SUITE.get(d, ()):
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
