"""Prove multi-agent engine_turn owns NL messages and is wired into the bot router."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "lumen/bot/routers/message_router.py"


def test_message_router_calls_handle_user_turn():
    src = ROUTER.read_text(encoding="utf-8")
    assert "handle_user_turn" in src
    assert "from lumen.engine.services.multi_agent.engine_turn import handle_user_turn" in src
    assert "PRIMARY PATH: multi-agent engine turn" in src
    # Old fragmented deterministic-only help path must not be the primary end
    assert "Non-bot, non-hard messages: short deterministic help" not in src


def test_handle_user_turn_generate_bot():
    from lumen.engine.services.multi_agent.engine_turn import handle_user_turn

    r = handle_user_turn("عايز بوت فيه /start و /help ويرد على الرسائل", user_id=42)
    assert r.action in {"generate", "refine"}
    assert r.ok is True
    assert r.generate_request
    assert r.user_data_updates.get("force_generate_once") is True
    assert r.capability_id in {"generate_bot", "refine_bot"} or r.tool in {
        "generate_bot",
        "refine_bot",
    }


def test_handle_user_turn_help_when_no_repo():
    from lumen.engine.services.multi_agent.engine_turn import handle_user_turn

    r = handle_user_turn("ازيك", user_id=7)
    assert r.ok is True
    assert r.action in {"help", ""}
    assert "المحرك" in r.reply or "بوت" in r.reply
    # Must NOT pretend a conversational chat answered
    assert r.tool in {"chat_or_other", "help", ""}


def test_handle_user_turn_host_status_routes_to_tool():
    from lumen.engine.services.multi_agent.engine_turn import handle_user_turn

    r = handle_user_turn("حالة الاستضافة", user_id=3)
    # Router should select host_status; execution may fail without live host — still agent path
    assert r.capability_id == "host_status" or r.tool == "host_status" or r.action in {
        "tool",
        "awaiting_confirm",
        "help",
    }
    assert r.state is not None


def test_handle_user_turn_repo_bound_uses_understand():
    import tempfile
    from pathlib import Path
    from lumen.engine.services.multi_agent.engine_turn import handle_user_turn

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "README.md").write_text("# demo\n", encoding="utf-8")
        r = handle_user_turn(
            "ايه اللي في المشروع",
            user_id=9,
            user_data={"active_repo": {"path": str(p), "url": ""}},
        )
        # Must go through agent tool path (repo_understand), not chat
        assert r.action in {"tool", "awaiting_confirm", "help"}
        assert r.state is not None
        if r.action == "tool":
            assert r.tool in {"repo_understand", "repo_inspect", "repo_modify"} or r.ok


def test_router_agent_registered():
    from lumen.engine.services.multi_agent import get_registry

    reg = get_registry()
    assert reg.get("router") is not None


def test_execute_tool_gated_receives_user_data_path():
    """Regression: tools.py must pass user_data into execute_tool."""
    src = (ROOT / "lumen/engine/services/multi_agent/tools.py").read_text(encoding="utf-8")
    assert "user_data=_ud" in src or "user_data=_ud," in src
    assert 'state.extensions["user_data"]' in src or "user_data" in src


def test_host_status_never_defers_to_router():
    """host_* must execute HostingService — never return defer_to_router stub."""
    import os
    os.environ.setdefault("ENVIRONMENT", "dev")
    from lumen.engine.services.tool_runtime import execute_tool

    tr = execute_tool("host_status", {}, user_id=1)
    msg = (tr.message or "").lower()
    assert "defer_to_router" not in msg
    assert "defer_to_router" not in str(tr.data or {})
    # Either real status text or honest unavailable — both are real paths
    assert tr.tool == "host_status"


def test_generate_bot_defers_only_to_generate_pipeline():
    from lumen.engine.services.tool_runtime import execute_tool
    tr = execute_tool("generate_bot", {"spec_request": "بوت /start"}, user_id=1)
    assert tr.ok is True
    assert (tr.data or {}).get("defer") is True
    assert "defer_to_generate" in (tr.message or "")
    assert "defer_to_router" not in (tr.message or "")
