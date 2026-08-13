"""Lightweight FAQ matcher from domain.yml — no TensorFlow / Rasa runtime.

Used when the trained NLU model is missing or broken (TF graph mismatch),
so DIALOGUE_ENABLED=1 still answers platform questions without freezing.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .contract import DialogueRequest, DialogueResponse
from .dynamic_answers import answer_for_intent

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]


class FaqEngine:
    name = "faq_v1"

    def __init__(self) -> None:
        self._examples: list[tuple[str, str]] | None = None  # (normalized example, intent)

    def available(self) -> bool:
        return True

    def _load(self) -> list[tuple[str, str]]:
        if self._examples is not None:
            return self._examples
        pairs: list[tuple[str, str]] = []
        try:
            import yaml
            nlu = _ROOT / "data" / "nlu.yml"
            if nlu.is_file():
                data = yaml.safe_load(nlu.read_text(encoding="utf-8")) or {}
                for block in data.get("nlu") or []:
                    if not isinstance(block, dict):
                        continue
                    intent = str(block.get("intent") or "").strip()
                    raw = block.get("examples") or ""
                    if not intent or not isinstance(raw, str):
                        continue
                    for line in raw.splitlines():
                        line = line.strip()
                        if line.startswith("-"):
                            line = line[1:].strip()
                        # strip markdown entity annotations [text](entity)
                        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
                        norm = _norm(line)
                        if norm and len(norm) >= 2:
                            pairs.append((norm, intent))
        except Exception:
            logger.exception("faq_engine failed to load nlu.yml")
        # Hardcoded high-value FAQ seeds (Arabic + English)
        seeds = {
            "greet": ["مرحبا", "السلام عليكم", "اهلا", "أهلا", "هاي", "hello", "hi", "صباح الخير"],
            "goodbye": ["باي", "مع السلامة", "الى اللقاء", "إلى اللقاء", "bye", "goodbye"],
            "ask_help": ["مساعدة", "help", "ساعدني", "ازاي ابدأ", "إزاي أبدأ"],
            "ask_pricing": ["السعر", "الاسعار", "الأسعار", "pricing", "كام السعر", "التكلفة"],
            "ask_current_plan": ["خطتي", "ما هي خطتي", "باقتي", "my plan", "current plan"],
            "ask_plan_comparison": ["مقارنة الخطط", "الفرق بين الخطط", "compare plans", "الخطط"],
            "how_platform_works": ["ازاي المنصة بتشتغل", "إزاي المنصة بتشتغل", "كيف تعمل", "how it works"],
            "ask_about_hosting": ["استضافة", "hosting", "استضافه"],
            "ask_about_preview": ["معاينة", "preview", "معاينه"],
            "project_identity": ["ما هو maestro", "ايه هو maestro", "what is maestro", "انت مين"],
            "bot_challenge": ["انت بوت", "are you a bot", "هل انت ذكاء"],
        }
        for intent, phrases in seeds.items():
            for p in phrases:
                pairs.append((_norm(p), intent))
        self._examples = pairs
        logger.info("FaqEngine loaded %s example phrases", len(pairs))
        return pairs

    def match_intent(self, text: str) -> tuple[str, float]:
        norm = _norm(text)
        if not norm:
            return "", 0.0
        best_intent = ""
        best_score = 0.0
        for ex, intent in self._load():
            if not ex:
                continue
            if norm == ex:
                return intent, 1.0
            if ex in norm or norm in ex:
                score = min(len(ex), len(norm)) / max(len(ex), len(norm))
                score = max(score, 0.72)
                if score > best_score:
                    best_score, best_intent = score, intent
            else:
                # token overlap
                et, nt = set(ex.split()), set(norm.split())
                if not et or not nt:
                    continue
                inter = len(et & nt)
                if inter == 0:
                    continue
                score = inter / max(len(et), len(nt))
                if score >= 0.6 and score > best_score:
                    best_score, best_intent = score, intent
        return best_intent, best_score

    async def handle(self, request: DialogueRequest) -> DialogueResponse | None:
        intent, conf = self.match_intent(request.text or "")
        if not intent or conf < 0.6:
            return None
        text = answer_for_intent(
            intent,
            sender_id=str(request.sender_id),
            fallback_plan_id=request.plan_id,
        )
        if not text:
            return None
        return DialogueResponse(
            text=text,
            intent=intent,
            confidence=conf,
            engine=self.name,
            slots={"plan_id": request.plan_id, "resolved_intent": intent},
            handled=True,
        )

    def status(self) -> dict[str, Any]:
        return {"faq_examples": len(self._load())}


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("ة", "ه").replace("ى", "ي").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = re.sub(r"[^\w\s\u0600-\u06ff]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t
