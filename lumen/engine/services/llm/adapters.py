"""Concrete adapters: vendor SDKs → TranslateProvider / ChatProvider ports.

Post multi-agent era (no deterministic catalog engine):
  chat      → Grok (xAI) primary, Groq fallback — fast responses
  translate → optional residual path (Groq/Gemini); generation goes multi-agent
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GroqTranslateAdapter:
    """Production translator (current default)."""

    name = "groq"

    def translate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from lumen.engine.services.translator_client import translate_via_groq

        return translate_via_groq(text, context)


class GeminiChatAdapter:
    """Production chat (current default)."""

    name = "gemini"

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from lumen.engine.services.translator_client import chat_via_gemini

        return chat_via_gemini(message, context)


class GeminiTranslateAdapter:
    """Translator — flattens gemini chat-wrapper into Groq-compatible contract.

    gemini_client.translate returns:
      {ok, answer, action, translation: {features_requested, spec_request, ...}}
    Bridge / force_generate / facade log expect TOP-LEVEL:
      features_requested, spec_request, confidence, purpose, clarification_needed
    Without flatten, preferred_keys stayed empty and only AR rules applied.
    """

    name = "gemini"

    def translate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            from lumen.engine.services.gemini_client import enabled, translate
        except Exception as exc:
            logger.warning("Gemini translate adapter import failed: %s", exc)
            return None
        if not enabled():
            logger.warning("Gemini translate adapter skipped (disabled / no key)")
            return None
        try:
            raw = translate(text, context or {})
        except Exception as exc:
            logger.exception("Gemini translate failed: %s", exc)
            return None
        if not isinstance(raw, dict):
            return None
        flat = self._flatten(raw)
        # High-precision rules override weak/wrong Gemini capability picks
        try:
            from lumen.engine.services.translator_client import (
                _rule_features_from_text,
                _spec_core_capabilities,
                _merge_features,
            )
            caps = set(_spec_core_capabilities() or [])
            rules = _rule_features_from_text(text or "", caps)
            model_feats = list(flat.get("features_requested") or [])
            merged = _merge_features(rules, model_feats, caps)
            if merged:
                flat["features_requested"] = merged
                flat["rule_features"] = list(rules)
                if rules and len(rules) >= 2:
                    flat["clarification_needed"] = False
                    flat["clarification_questions"] = []
                    if float(flat.get("confidence") or 0) < 0.8:
                        flat["confidence"] = 0.9
                    # Ensure spec_request mentions real features when model drifted
                    if rules and not any(
                        str(x).startswith("pdf") or str(x) == "images_to_pdf"
                        for x in model_feats
                    ):
                        flat["spec_request"] = (
                            (flat.get("spec_request") or flat.get("purpose") or "Telegram bot")
                            + " | features: "
                            + ", ".join(merged)
                        )
        except Exception as exc:
            logger.warning("Gemini rule-merge skipped: %s", exc)
        return flat

    @staticmethod
    def _flatten(raw: dict[str, Any]) -> dict[str, Any]:
        nested = raw.get("translation") if isinstance(raw.get("translation"), dict) else {}
        # Prefer nested translation fields; fall back to top-level if already flat
        def _get(key: str, default=None):
            if key in nested and nested.get(key) not in (None, "", []):
                return nested.get(key)
            return raw.get(key, default)

        features = _get("features_requested") or []
        if not isinstance(features, list):
            features = []
        features = [str(x).strip() for x in features if str(x).strip()]

        # Canonicalize against catalog + aliases (content_list → shop_catalog, etc.)
        try:
            from lumen.engine.services.translator_client import (
                _canonicalize_features,
                _spec_core_capabilities,
                _rule_features_from_text,
            )
            caps = set(_spec_core_capabilities() or [])
            features = _canonicalize_features(features, caps) if caps else features
            # Drop anything still outside catalog (Gemini invents keys like del_forbidden)
            if caps:
                features = [k for k in features if k in caps]
        except Exception:
            caps = set()

        purpose = str(_get("purpose") or "").strip()
        spec_request = str(_get("spec_request") or "").strip()
        try:
            confidence = float(_get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        clarification = bool(_get("clarification_needed") or False)
        questions = _get("clarification_questions") or []
        if not isinstance(questions, list):
            questions = []
        flows = _get("flows") or []
        if not isinstance(flows, list):
            flows = []

        action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
        flat = {
            "purpose": purpose,
            "features_requested": features,
            "flows": [str(x).strip() for x in flows if str(x).strip()][:20],
            "strict_spec": bool(_get("strict_spec") or False),
            "confidence": max(0.0, min(1.0, confidence)),
            "clarification_needed": clarification,
            "clarification_questions": [str(x).strip() for x in questions if str(x).strip()][:5],
            "spec_request": spec_request,
            "model": str(raw.get("model") or nested.get("model") or "gemini"),
            "source": str(raw.get("source") or "gemini"),
            "engine_mode": str(_get("engine_mode") or "cline"),
            # keep chat fields for message_router dual-use paths
            "ok": bool(raw.get("ok", True)),
            "answered": bool(raw.get("answered", True)),
            "answer": str(raw.get("answer") or "").strip(),
            "action": action,
            "translation": {
                "purpose": purpose,
                "features_requested": features,
                "flows": [str(x).strip() for x in flows if str(x).strip()][:20],
                "strict_spec": bool(_get("strict_spec") or False),
                "confidence": max(0.0, min(1.0, confidence)),
                "clarification_needed": clarification,
                "clarification_questions": [str(x).strip() for x in questions if str(x).strip()][:5],
                "spec_request": spec_request,
                "model": str(raw.get("model") or "gemini"),
            },
        }
        return flat


class GroqChatAdapter:
    """Production chat (step 2 default) — same JSON contract as Gemini chat."""

    name = "groq"

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from lumen.engine.services.llm.groq_chat import chat_via_groq

        return chat_via_groq(message, context)


class GrokChatAdapter:
    """xAI Grok chat — preferred primary for speed."""

    name = "xai"

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from lumen.engine.services.llm.grok_chat import chat_via_grok

        return chat_via_grok(message, context)


__all__ = [
    "GroqTranslateAdapter",
    "GeminiChatAdapter",
    "GeminiTranslateAdapter",
    "GroqChatAdapter",
    "GrokChatAdapter",
]
