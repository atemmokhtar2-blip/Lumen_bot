"""Language Understanding (L1) + Intent Analysis (L2) — zero-AI foundation."""
from .engine import (
    DOMAIN_TO_PRESET,
    DomainSignal,
    LanguageUnderstandingResult,
    understand,
)
from .entities import ExtractedEntities, extract_entities
from .intent_analysis import (
    ASK_THRESHOLD,
    IntentAnalysis,
    IntentSignal,
    analyze,
    analyze_intent,
    detect_language,
)
from .normalize import light_stem_ar, normalize_text, tokenize

__all__ = [
    "understand",
    "LanguageUnderstandingResult",
    "DomainSignal",
    "DOMAIN_TO_PRESET",
    "ExtractedEntities",
    "extract_entities",
    "normalize_text",
    "tokenize",
    "light_stem_ar",
    "analyze",
    "analyze_intent",
    "IntentAnalysis",
    "IntentSignal",
    "detect_language",
    "ASK_THRESHOLD",
]
