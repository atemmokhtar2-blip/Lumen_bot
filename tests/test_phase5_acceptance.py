"""Phase 5: acceptance gates block empty/broken projects."""
from pathlib import Path


def test_check_agent_project_empty(tmp_path: Path):
    from lumen.engine.services.cline_runtime.agent_acceptance import check_agent_project
    acc = check_agent_project(tmp_path, goal="بوت تيليجرام")
    assert acc.get("ok") is False
    assert acc.get("missing")


def test_check_agent_project_minimal_ok(tmp_path: Path):
    from lumen.engine.services.cline_runtime.agent_acceptance import check_agent_project
    (tmp_path / "main.py").write_text(
        "import os\nfrom telegram import Update\n\ndef main():\n    t = os.getenv('BOT_TOKEN')\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("python-telegram-bot\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# bot\n", encoding="utf-8")
    acc = check_agent_project(tmp_path, goal="telegram bot")
    assert acc.get("ok") is True, acc


def test_check_agent_project_syntax_fail(tmp_path: Path):
    from lumen.engine.services.cline_runtime.agent_acceptance import check_agent_project
    (tmp_path / "main.py").write_text("def broken(\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    acc = check_agent_project(tmp_path)
    assert acc.get("ok") is False
    assert any("entry_syntax" in str(m) or "syntax" in str(m) for m in (acc.get("missing") or []))


def test_coding_session_agent_acceptance_in_result(tmp_path: Path):
    import os
    from unittest.mock import patch
    os.environ["OPENAI_API_KEY"] = "sk-x"
    os.environ["CLINE_ROUTER"] = "local"
    for k in ("AZURE_FOUNDRY_KEY", "DEEPSEEK_API_KEY"):
        os.environ.pop(k, None)
    from lumen.engine.services.multi_agent.coding_agent import run_coding_session
    from lumen.engine.services.cline_runtime.agent_state import AgentState

    st = AgentState(work_dir=str(tmp_path), goal="g")
    st.ok = True
    st.metadata = {"router": {"provider": "openai", "model_id": "gpt-4o-mini"}}
    with patch(
        "lumen.engine.services.cline_runtime.agent_loop.run_agent",
        return_value=st,
    ):
        out = run_coding_session(work_dir=tmp_path, goal="echo bot", user_id=1)
    assert out.get("ok") is False  # empty project fails agent acceptance
    assert isinstance(out.get("agent_acceptance"), dict)
    assert out["agent_acceptance"].get("ok") is False
