"""Cline runtime boundary — general execution under Core IR + policies."""
from __future__ import annotations

from .executor import ClineExecutionResult, execute_cline_ir, is_cline_available
from .model_router import describe_runtime, select_model
from .mcp_bridge import status as mcp_status

__all__ = [
    "ClineExecutionResult",
    "describe_runtime",
    "execute_cline_ir",
    "is_cline_available",
    "mcp_status",
    "select_model",
]
