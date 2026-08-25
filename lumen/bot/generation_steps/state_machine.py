"""Delivery pipeline states (post code-generation).

IntentExtraction / SpecComposition / CodeGeneration live upstream
(in capability + coding engines). This module owns the post-build
delivery chain only:

  SUMMARY -> NARRATIVE -> VALIDATE (smoke + anti-hallucination)
           -> PACKAGE (zip) -> TOKEN_READY -> DONE

`deliver_generation_result` is the orchestrator entry point.
"""
from __future__ import annotations

from enum import Enum, auto

class GenerationPhase(Enum):
    INTENT_EXTRACTION = auto()   # upstream
    SPEC_COMPOSITION = auto()    # upstream
    CODE_GENERATION = auto()     # upstream
    VALIDATION = auto()          # smoke + anti-hallucination
    PACKAGING = auto()           # zip + status
    TOKEN_READY = auto()         # pending deploy session

from .delivery import deliver_generation_result

__all__ = ["GenerationPhase", "deliver_generation_result"]
