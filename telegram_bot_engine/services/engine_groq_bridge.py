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

    model_feats = [
        str(x).strip()
        for x in (tr.get("features_requested") or [])
        if str(x).strip()
    ]
    rules = _rule_features(original)
    # Prefer rules + model; dedupe; keep only catalog keys for the engine
    preferred: list[str] = []
    for key in rules + model_feats:
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

    package = {
        "original_text": original,
        "spec_request": engine_request,
        "preferred_keys": preferred[:12],
        "engine_mode": "ai_codegen" if needs_ai else "spec_core",
        "needs_ai_codegen": bool(needs_ai),
        "confidence": confidence,
        "model": tr.get("model") or "rules",
        "purpose": purpose,
        "rule_features": rules,
        "notes": [],
    }
    if needs_ai:
        package["notes"].append("out_of_catalog_or_custom_stack")
    logger.info(
        "engine_groq_bridge mode=%s keys=%s conf=%.2f model=%s",
        package["engine_mode"],
        package["preferred_keys"],
        confidence,
        package["model"],
    )
    return package
