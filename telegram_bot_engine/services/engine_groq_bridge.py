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
    """Map user-written /commands to registry keys. Always wins over model cart noise."""
    import re
    try:
        from telegram_bot_engine.spec_core.builder import DEFAULT_COMMANDS
    except Exception:
        DEFAULT_COMMANDS = {}
    cmd_to_feat: dict[str, str] = {}
    for feat, cmd in (DEFAULT_COMMANDS or {}).items():
        if isinstance(cmd, str) and cmd.strip():
            cmd_to_feat.setdefault(cmd.strip().lower(), str(feat))
    cmd_to_feat.update({
        "products": "shop_catalog", "product": "shop_catalog", "catalog": "shop_catalog",
        "shop": "shop_catalog", "order": "shop_order", "orders": "shop_orders",
        "add": "task_add", "list": "task_list", "done": "task_done",
        "delete": "task_delete", "ticket": "ticket_open", "about": "about",
        "welcome": "welcome_set", "setwelcome": "welcome_set",
    })
    out: list[str] = []
    for m in re.finditer(r"(?<!\w)/([A-Za-z][A-Za-z0-9_]{0,31})", text or ""):
        cid = m.group(1).lower()
        feat = cmd_to_feat.get(cid)
        if feat and feat in catalog and feat not in out:
            out.append(feat)
        elif cid in catalog and cid not in out:
            out.append(cid)
    return out


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
    # Root: user slash commands beat Groq model features (e.g. /products over cart_*)
    slash_feats = _slash_features_from_text(original, catalog)
    preferred: list[str] = []
    for key in slash_feats + rules + model_feats:
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

    package = {
        "original_text": original,
        "spec_request": engine_request,
        "preferred_keys": preferred[:12],
        "engine_mode": "ai_codegen" if needs_ai else "spec_core",
        "needs_ai_codegen": bool(needs_ai),
        "confidence": max(confidence, 0.9 if rules else confidence),
        "model": tr.get("model") or "rules",
        "purpose": purpose,
        "rule_features": rules,
        "notes": ["keys_bound"] if preferred else [],
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
