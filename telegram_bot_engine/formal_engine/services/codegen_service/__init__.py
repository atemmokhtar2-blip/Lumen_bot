"""Codegen — Formal DSL path only. No templates."""
from .service import CodegenService, generate_from_contract, generate_from_text

__all__ = ["CodegenService", "generate_from_contract", "generate_from_text"]
