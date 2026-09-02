"""Local tool runtime — Groq only *selects* tools; engines execute them."""
from .registry import TOOL_SPECS, list_tool_names
from .executor import ToolResult, execute_tool, run_tools_parallel

__all__ = [
    "TOOL_SPECS",
    "list_tool_names",
    "ToolResult",
    "execute_tool",
    "run_tools_parallel",
]
