"""Experimental Groq direct code generation (optional path when enabled)."""
from .service import generate_bot_via_groq, enabled as groq_codegen_enabled

__all__ = ["generate_bot_via_groq", "groq_codegen_enabled"]
