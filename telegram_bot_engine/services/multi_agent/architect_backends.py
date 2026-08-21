"""Pluggable StrictSpec producers for the Architect role (extensible)."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from .strict_spec import StrictSpec, merge_spec_request

logger = logging.getLogger(__name__)


class SpecBackend(ABC):
    name: str = "base"
    priority: int = 100  # lower runs first

    @abstractmethod
    def produce(self, view: dict[str, Any]) -> Optional[StrictSpec]:
        """Return StrictSpec or None to try next backend."""


class GeminiSpecBackend(SpecBackend):
    """Gemini produces structured plan only — never user-facing chat."""

    name = "gemini"
    priority = 10

    def produce(self, view: dict[str, Any]) -> Optional[StrictSpec]:
        if (os.environ.get("MULTI_AGENT_GEMINI_ARCHITECT") or "1").strip().lower() in {
            "0", "false", "no", "off",
        }:
            return None
        text = str(view.get("user_text") or "").strip()
        if not text:
            return None
        try:
            from telegram_bot_engine.services import gemini_client
            if not gemini_client.enabled():
                return None
            # Isolated context — no chat persona, translate mode only
            ctx = {
                "mode_hint": "architect_strict_spec",
                "user_intent": view.get("user_intent"),
                "capability_id": view.get("capability_id"),
                "preferred_keys_hint": view.get("preferred_keys_hint") or [],
                "qa_summary": view.get("qa_summary"),
                # Keep capability list small if available
            }
            try:
                from telegram_bot_engine.spec_core.registry import CAPABILITIES
                ctx["spec_core_capabilities"] = sorted(list(CAPABILITIES.keys()))[:200]
            except Exception:
                ctx["spec_core_capabilities"] = []

            # Dedicated architect mode (no user-facing answer)
            if hasattr(gemini_client, "architect_spec"):
                result = gemini_client.architect_spec(text, ctx)
            else:
                result = gemini_client.translate(text, ctx)
            if not isinstance(result, dict) or not result.get("ok", True):
                return None
            tr = result.get("translation") or {}
            if not (tr.get("spec_request") or tr.get("purpose") or tr.get("features_requested")):
                return None
            spec = StrictSpec.from_dict({
                **tr,
                "features": tr.get("features_requested") or tr.get("features") or [],
                "source": str(result.get("source") or "gemini_architect"),
                "model": result.get("model") or tr.get("model") or "",
                "domain": tr.get("domain") or "",
            })
            # Architect must not store user-facing answer on the board
            if not spec.spec_request:
                spec.spec_request = merge_spec_request(spec)
            return spec
        except Exception as exc:
            logger.warning("GeminiSpecBackend failed: %s", type(exc).__name__)
            return None


class BridgeSpecBackend(SpecBackend):
    name = "bridge"
    priority = 20

    def produce(self, view: dict[str, Any]) -> Optional[StrictSpec]:
        text = str(view.get("user_text") or "").strip()
        if not text:
            return None
        try:
            from telegram_bot_engine.services.engine_groq_bridge import analyze_and_prepare
            package = analyze_and_prepare(text, None)
            features = package.get("preferred_keys") or []
            if isinstance(features, dict):
                features = features.get("preferred_keys") or []
            spec = StrictSpec(
                purpose=str(package.get("preset_hint") or package.get("domain_hint") or "")[:500],
                domain=str(package.get("domain_hint") or "")[:120],
                features=list(features)[:80] if isinstance(features, (list, tuple)) else [],
                spec_request=str(package.get("spec_request") or text)[:20000],
                confidence=0.55,
                source="bridge",
                raw={"needs_ai_codegen": bool(package.get("needs_ai_codegen"))},
            )
            return spec
        except Exception as exc:
            logger.warning("BridgeSpecBackend failed: %s", type(exc).__name__)
            return None


class DeterministicSpecBackend(SpecBackend):
    """Last-resort — always returns something buildable from raw text."""

    name = "deterministic"
    priority = 90

    def produce(self, view: dict[str, Any]) -> Optional[StrictSpec]:
        text = str(view.get("user_text") or "").strip()
        intent = str(view.get("user_intent") or "")
        keys = list(view.get("preferred_keys_hint") or [])
        if not text and not keys:
            return None
        req = text
        if req and "بوت" not in req and "bot" not in req.lower():
            req = f"بوت تيليجرام: {req}"
        return StrictSpec(
            purpose=text[:300],
            features=keys[:40],
            spec_request=req[:20000],
            confidence=0.35,
            source="deterministic",
            language="ar",
        )


def default_backends() -> list[SpecBackend]:
    return [GeminiSpecBackend(), BridgeSpecBackend(), DeterministicSpecBackend()]


def produce_strict_spec(view: dict[str, Any], backends: list[SpecBackend] | None = None) -> StrictSpec:
    chain = sorted(backends or default_backends(), key=lambda b: int(b.priority))
    errors: list[str] = []
    for backend in chain:
        try:
            spec = backend.produce(view)
        except Exception as exc:
            errors.append(f"{backend.name}:{type(exc).__name__}")
            continue
        if spec is None:
            errors.append(f"{backend.name}:none")
            continue
        # Accept first non-null; prefer buildable
        if spec.is_buildable() or backend.name == "deterministic":
            if not spec.spec_request:
                spec.spec_request = merge_spec_request(spec)
            spec.raw = {**(spec.raw or {}), "backend_chain": errors + [f"{backend.name}:ok"]}
            return spec
        errors.append(f"{backend.name}:not_buildable")
    # Absolute fallback
    return StrictSpec(
        purpose="fallback",
        spec_request=str(view.get("user_text") or "بوت"),
        source="fallback",
        confidence=0.1,
        raw={"backend_chain": errors},
    )
