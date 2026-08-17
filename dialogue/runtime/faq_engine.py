"""Strict dialogue fallback.

This module intentionally does not read nlu.yml, domain.yml, or hardcoded FAQ
phrases. Dialogue answers must come from a trained model plus live runtime
context. When the trained model is unavailable, returning None is safer than
returning a static or guessed answer.
"""
from __future__ import annotations

from typing import Any

from .contract import DialogueRequest, DialogueResponse


class FaqEngine:
    name = "disabled_static_fallback"

    def available(self) -> bool:
        return False

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        return None

    def status(self) -> dict[str, Any]:
        return {"faq_examples": 0, "static_fallback": False}
