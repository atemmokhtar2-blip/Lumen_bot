"""Web research + safe auto-update for zero-AI bot packs."""
from .research import research_stack, ResearchReport
from .apply import run_update, apply_research, ApplyResult
__all__ = ["research_stack", "ResearchReport", "run_update", "apply_research", "ApplyResult"]
