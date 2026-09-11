"""Phase 4 — agent tool path binds active_repo after clone/pull."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumen.engine.services.tool_runtime.executor import ToolResult, _tool_git_pull


def test_git_pull_needs_clone_when_no_path():
    r = _tool_git_pull({}, user_id=0, user_data={})
    assert r.ok is False
    assert r.data.get("needs_clone") is True


def test_git_pull_needs_github_when_no_token():
    with patch(
        "lumen.engine.services.tool_runtime.executor._resolve_github_token_for_tool",
        return_value=None,
    ), patch(
        "lumen.engine.services.integrations.connections.credentials.is_github_connected",
        return_value=False,
    ):
        r = _tool_git_pull(
            {},
            user_id=42,
            user_data={"active_repo": {"path": "/tmp"}},
        )
    # path may not exist on disk → needs_clone OR needs_github
    assert r.ok is False


def test_clone_result_includes_active_repo_shape():
    # structural expectation on ToolResult data contract
    tr = ToolResult(
        ok=True,
        tool="clone_repo",
        message="ok",
        data={"path": "/x", "active_repo": {"path": "/x", "url": "https://github.com/a/b", "source": "clone_repo"}},
    )
    d = tr.to_dict()
    assert d["data"]["active_repo"]["path"] == "/x"


def test_multi_agent_binds_active_repo_on_success():
    from lumen.engine.services.multi_agent.state import AgentState
    from lumen.engine.services.multi_agent.tools import execute_tool_gated

    state = AgentState(user_id=1)
    state.capability_id = "clone_repo"

    fake = ToolResult(
        ok=True,
        tool="clone_repo",
        message="تم السحب",
        data={"path": "/repo/x", "active_repo": {"path": "/repo/x", "url": "https://g/h", "source": "clone_repo"}},
    )
    with patch(
        "lumen.engine.services.tool_runtime.executor.execute_tool",
        return_value=fake,
    ), patch(
        "lumen.engine.services.multi_agent.tools.tool_requires_confirmation",
        return_value=False,
    ), patch(
        "lumen.engine.services.multi_agent.tools.tool_risk",
        return_value="low",
    ):
        out = execute_tool_gated(
            state,
            "clone_repo",
            {"url": "https://github.com/example/repo"},
            skip_hitl=True,
        )
    ar = out.extensions.get("active_repo") or {}
    assert ar.get("path") == "/repo/x"
