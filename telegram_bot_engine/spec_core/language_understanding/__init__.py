"""L1 LU + L2 Intent + L3 Adaptive Questions + L4 Memory."""
from .adaptive_questioning import (
    AdaptiveQuestion,
    QuestionPlan,
    apply_answer,
    build_question_plan,
    next_questions,
)
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
from .memory_engine import (
    MemoryEngine,
    SessionMemory,
    UserProfile,
    get_memory_engine,
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
    "build_question_plan",
    "next_questions",
    "apply_answer",
    "AdaptiveQuestion",
    "QuestionPlan",
    "MemoryEngine",
    "SessionMemory",
    "UserProfile",
    "get_memory_engine",
]
