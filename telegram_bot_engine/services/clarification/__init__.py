"""Clarification service — rule-based, zero LLM."""

from .service import (
    ClarificationResult,
    assess_spec,
    merge_answers,
    build_clarification_message,
)

__all__ = [
    "ClarificationResult",
    "assess_spec",
    "merge_answers",
    "build_clarification_message",
]
