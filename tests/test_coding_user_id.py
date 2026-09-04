
def test_run_coding_session_injects_user_id(tmp_path):
    import os
    from unittest.mock import patch
    os.environ["OPENAI_API_KEY"] = "sk-x"
    for k in ("AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT", "DEEPSEEK_API_KEY"):
        os.environ.pop(k, None)
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.multi_agent.coding_agent import run_coding_session
    from lumen.engine.services.cline_runtime import agent_brain
    from lumen.engine.services.cline_runtime.agent_state import AgentState

    captured = {}

    def fake_run_agent(**kwargs):
        captured["ir"] = kwargs.get("ir_dict") or {}
        st = AgentState(work_dir=str(tmp_path), goal="g")
        st.ok = False
        st.metadata = {"router": {"provider": "openai", "model_id": "gpt-4o-mini"}, "user_id": captured["ir"].get("user_id")}
        return st

    with patch("lumen.engine.services.cline_runtime.agent_loop.run_agent", side_effect=fake_run_agent):
        out = run_coding_session(work_dir=tmp_path, goal="echo", user_id=4242)
    assert captured["ir"].get("user_id") == 4242
    assert out.get("user_id") == 4242
