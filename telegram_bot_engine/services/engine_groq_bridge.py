"""Bridge between Groq translation and the deterministic spec_core engine.

Goal: engine stays primary; Groq supplies intent/features and only assists
when the request is outside the capability catalog.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _catalog() -> set[str]:
    try:
        from telegram_bot_engine.services.translator_client import _spec_core_capabilities
        caps = _spec_core_capabilities()
        if caps:
            return set(caps)
    except Exception:
        pass
    return {
        "start", "help", "welcome_set", "user_ban", "user_warn", "user_mute",
        "rules", "delete_message", "user_kick", "user_unban",
    }


def _rule_features(text: str) -> list[str]:
    try:
        from telegram_bot_engine.services.translator_client import (
            _rule_features_from_text,
        )
        return _rule_features_from_text(text or "", _catalog())
    except Exception:
        return []


def _slash_features_from_text(text: str, catalog: set[str]) -> list[str]:
    """User-written /commands → features (canonical command_map only)."""
    from telegram_bot_engine.spec_core.command_map import features_from_text
    feats = features_from_text(text or "", include_core=False)
    return [f for f in feats if f in catalog] if catalog else feats


def analyze_and_prepare(
    user_text: str,
    translation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a normalized handoff package for generation.

    Keys:
      original_text, spec_request, preferred_keys, engine_mode,
      needs_ai_codegen, confidence, model, notes
    """
    catalog = _catalog()
    original = (user_text or "").strip()
    tr = translation if isinstance(translation, dict) else {}
    # Gemini may nest under translation{} — accept both shapes
    nested = tr.get("translation") if isinstance(tr.get("translation"), dict) else {}
    model_feats_raw = tr.get("features_requested") or nested.get("features_requested") or []
    model_feats = [
        str(x).strip()
        for x in model_feats_raw
        if str(x).strip()
    ]
    # Prefer nested purpose/spec when top-level empty
    if not str(tr.get("spec_request") or "").strip() and nested.get("spec_request"):
        tr = dict(tr)
        tr["spec_request"] = nested.get("spec_request")
    if not str(tr.get("purpose") or "").strip() and nested.get("purpose"):
        tr = dict(tr)
        tr["purpose"] = nested.get("purpose")
    if tr.get("confidence") in (None, 0, 0.0) and nested.get("confidence"):
        tr = dict(tr)
        tr["confidence"] = nested.get("confidence")
    rules = _rule_features(original)
    # Root: user slash commands beat Groq model features (e.g. /products over cart_*)
    slash_feats = _slash_features_from_text(original, catalog)
    # When rules are weak (no domain keys), pull capability detection so
    # preferred_keys is not stuck at start/help for shop/tasks/etc.
    det_feats: list[str] = []
    if len([k for k in rules if k not in {"start", "help"}]) == 0:
        try:
            from telegram_bot_engine.services.capability_detection.integration import (
                feature_keys,
                run_detection,
            )
            det_feats = [
                k for k in feature_keys(run_detection(original), include_core=False)
                if k in catalog
            ]
        except Exception:
            det_feats = []
    preferred: list[str] = []
    for key in slash_feats + rules + model_feats + det_feats:
        if key in catalog and key not in preferred:
            preferred.append(key)
    if not preferred:
        preferred = [k for k in ("start", "help") if k in catalog]

    # Always ensure start/help when building a bot
    for core in ("start", "help"):
        if core in catalog and core not in preferred:
            preferred.append(core)

    spec = str(tr.get("spec_request") or "").strip()
    purpose = str(tr.get("purpose") or "").strip()

    # Engine understands both Arabic original and English brief together
    if spec and original and original not in spec:
        engine_request = f"{original}\n\n{spec}"
        if purpose and purpose not in engine_request:
            engine_request = f"{engine_request}\nPurpose: {purpose}"
    elif original:
        engine_request = original
        if purpose:
            engine_request = f"{original}\n\nPurpose: {purpose}"
    else:
        engine_request = spec or purpose or "Telegram bot with start and help"

    # Out-of-catalog signal: model asked clarification with empty/weak features,
    # or user text is long/custom while rules found almost nothing beyond start/help.
    custom_markers = (
        "api", "webhook", "stripe", "openai", "gpt", "database", "postgres",
        "mongo", "redis", "selenium", "scrap", "nft", "crypto", "ai ", "chatgpt",
        "تكامل", "ربط مع", "api خارجي", "ذكاء اصطناعي", "شات جي بي تي",
    )
    lower = original.lower()
    looks_custom = any(m in lower for m in custom_markers)
    weak_rules = len([k for k in rules if k not in {"start", "help"}]) == 0
    confidence = float(tr.get("confidence") or (0.85 if rules else 0.5))

    needs_ai = False
    if looks_custom and weak_rules:
        needs_ai = True
    if (tr.get("needs_ai_codegen") is True) or (
        str(tr.get("engine_mode") or "").lower() == "ai_codegen"
    ):
        needs_ai = True
    # Optional: force hybrid assist only when explicitly enabled
    assist_flag = (os.getenv("GROQ_ASSIST_OUT_OF_SCOPE") or "1").strip().lower()
    if assist_flag in {"0", "false", "no", "off"}:
        needs_ai = False

    # Prefer slash (user-written) → rules → model; never drop slash keys
    ordered: list[str] = []
    for k in list(slash_feats) + list(rules) + list(preferred):
        if k not in ordered:
            ordered.append(k)
    preferred = ordered[:16] or preferred[:16]

    # Strong binding string the engine can also keyword-match
    if preferred:
        bind_line = "CAPABILITY_KEYS: " + ", ".join(preferred)
        if bind_line not in engine_request:
            engine_request = f"{engine_request}\n\n{bind_line}"

    # Catalog match vs gap (control-plane IR fields)
    core = {"start", "help", "lang", "language", "cancel"}
    matched = [k for k in preferred if k not in core]
    # Heuristic gaps: custom markers not covered by catalog keys
    integrations: list[str] = []
    gap: list[str] = []
    if looks_custom:
        for marker, label in (
            ("stripe", "payment_gateway"),
            ("paypal", "payment_gateway"),
            ("openai", "llm_api"),
            ("gpt", "llm_api"),
            ("chatgpt", "llm_api"),
            ("webhook", "webhook"),
            ("postgres", "external_db"),
            ("mongo", "external_db"),
            ("redis", "external_db"),
            ("تكامل", "external_integration"),
            ("api خارجي", "external_api"),
            ("ذكاء اصطناعي", "llm_api"),
        ):
            if marker in lower and label not in integrations:
                integrations.append(label)
                if label not in gap:
                    gap.append(label)
    if needs_ai and not matched:
        if "out_of_catalog" not in gap:
            gap.append("out_of_catalog")

    # New engine modes: catalog | hybrid | cline (legacy aliases kept in notes)
    try:
        from telegram_bot_engine.services.engine_router import decide_engine_mode
        mode = decide_engine_mode(
            preferred_keys=preferred,
            capabilities_gap=gap,
            looks_custom=looks_custom,
            needs_ai_codegen=bool(needs_ai),
            confidence=float(confidence or 0.0),
        )
        engine_mode = mode.value
    except Exception:
        engine_mode = "cline" if needs_ai else "catalog"

    package = {
        "original_text": original,
        "spec_request": engine_request,
        "preferred_keys": preferred[:12],
        "capabilities_matched": matched[:16],
        "capabilities_gap": gap[:16],
        "integrations": integrations[:12],
        "looks_custom": bool(looks_custom),
        "engine_mode": engine_mode,
        # legacy fields for older callers
        "needs_ai_codegen": bool(needs_ai),
        "confidence": max(confidence, 0.9 if rules else confidence),
        "model": tr.get("model") or "rules",
        "purpose": purpose,
        "rule_features": rules,
        "notes": ["keys_bound"] if preferred else [],
    }
    if needs_ai:
        package["notes"].append("out_of_catalog_or_custom_stack")
    package["notes"].append(f"engine_mode:{engine_mode}")
    logger.info(
        "engine_groq_bridge mode=%s keys=%s gap=%s conf=%.2f model=%s",
        package["engine_mode"],
        package["preferred_keys"],
        package["capabilities_gap"],
        confidence,
        package["model"],
    )
    return package
