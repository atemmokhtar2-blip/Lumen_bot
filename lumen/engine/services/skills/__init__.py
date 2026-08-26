"""Open Skills / plugins registry + MCP client (JSON-RPC over HTTP/SSE)."""
from __future__ import annotations

from .registry import (
    Skill,
    SkillRegistry,
    get_registry,
    list_skills,
    register_skill,
    run_skill,
)
from .mcp_client import MCPClient, mcp_list_tools, mcp_call_tool

__all__ = [
    "Skill",
    "SkillRegistry",
    "get_registry",
    "list_skills",
    "register_skill",
    "run_skill",
    "MCPClient",
    "mcp_list_tools",
    "mcp_call_tool",
]
