"""Error Intelligence — deterministic log understanding for LiveRunner + hosting foundation."""

from .service import ErrorIntelligenceService, analyze_logs, diagnose_live_report

__all__ = [
    "ErrorIntelligenceService",
    "analyze_logs",
    "diagnose_live_report",
]
