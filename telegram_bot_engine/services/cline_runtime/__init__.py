"""Cline runtime boundary — general execution under Core IR + policies.

This package does NOT replace catalog generation. Core selects:
  catalog | hybrid | cline

When CLINE_SDK is not installed or CLINE_ENABLED=0, the runtime degrades
safely to catalog/hybrid paths instead of inventing bots.
"""
from __future__ import annotations

from .executor import ClineExecutionResult, execute_cline_ir, is_cline_available

__all__ = [
    "ClineExecutionResult",
    "execute_cline_ir",
    "is_cline_available",
]
