"""Every agent tool name in the prompt must dispatch (not unknown_tool)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lumen.engine.services.cline_runtime.agent_loop import AGENT_TOOL_NAMES, _system_prompt, _tools_help
from lumen.engine.services.cline_runtime.agent_fs import run_tool


def test_system_prompt_lists_all_dispatchable_tools():
    help_s = _tools_help()
    prompt = _system_prompt("/tmp/ws", "build a bot", None)
    for name in AGENT_TOOL_NAMES:
        assert name in help_s, name
        assert name in prompt, f"prompt missing {name}"


def test_no_tool_is_unknown_tool():
    work = Path(tempfile.mkdtemp())
    (work / "main.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    for name in AGENT_TOOL_NAMES:
        args = {
            "path": "main.py",
            "pattern": "hello",
            "query": "hello",
            "name": "hello",
            "content": "x=1\n",
            "old_string": "return 1",
            "new_string": "return 2",
            "paths": ["main.py"],
            "edits": [],
            "patch": "",
            "url": "https://example.com",
            "session_id": "",
            "selector": "a",
            "value": "1",
            "command": "echo hi",
            "arguments": {},
        }
        r = run_tool(str(work), name, args)
        assert not str(r.get("error") or "").startswith("unknown_tool"), (name, r)


def test_builtin_catalog_blocked_by_default():
    import os
    os.environ.pop("CLINE_ALLOW_BUILTIN", None)
    os.environ["CLINE_MODE"] = "agent"
    from lumen.engine.services.multi_agent.production_policy import allow_cline_builtin
    assert allow_cline_builtin() is False
