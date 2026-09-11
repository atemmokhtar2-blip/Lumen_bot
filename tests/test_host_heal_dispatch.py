"""host_heal must be dispatched by execute_tool (not unknown_tool)."""
from __future__ import annotations
import os
os.environ.setdefault("ENVIRONMENT", "test")
from unittest.mock import MagicMock, patch
from lumen.engine.services.tool_runtime.executor import execute_tool, ToolResult

def test_host_heal_not_unknown():
    fake = ToolResult(ok=True, tool="host_heal", message="المثيل سليم", data={"healthy": True})
    with patch("lumen.engine.services.tool_runtime.executor._tool_host", return_value=fake):
        r = execute_tool("host_heal", {}, user_id=1, user_data={})
    assert r.tool == "host_heal"
    assert "غير معروفة" not in (r.message or "")
