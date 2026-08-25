"""Anti-hallucination gate — block false claims about generated bots."""
from .gate import (
    AntiHallucinationReport,
    run_anti_hallucination_gate,
    verified_capabilities_summary,
)

__all__ = [
    "AntiHallucinationReport",
    "run_anti_hallucination_gate",
    "verified_capabilities_summary",
]
