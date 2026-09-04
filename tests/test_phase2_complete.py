"""Phase 2: real provider callers + catalog-bound model ids."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


def _clear():
    for k in list(os.environ):
        if any(x in k for x in (
            "API_KEY", "FOUNDRY", "CLINE_", "GEMINI", "GOOGLE", "DEEPSEEK",
            "OPENAI", "GROQ", "ANTHROPIC", "OPENROUTER", "AZURE", "ENGINE_LLM",
        )):
            os.environ.pop(k, None)


def test_deepseek_v3_model_id_is_chat_not_pro():
    _clear()
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    m = mc.get_model("deepseek-v3")
    assert m.model_id == "deepseek-chat"
    # DEEPSEEK_MODEL must not pollute V3
    os.environ["DEEPSEEK_MODEL"] = "deepseek-v4-pro"
    reload(mc)
    assert mc.get_model("deepseek-v3").model_id == "deepseek-chat"
    os.environ["DEEPSEEK_V3_MODEL"] = "deepseek-chat"
    reload(mc)
    assert mc.get_model("deepseek-v3").model_id == "deepseek-chat"


def test_dispatch_uses_catalog_id_over_provider_first():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    from lumen.engine.services.cline_runtime.model_router import ModelChoice
    from lumen.engine.services.cline_runtime import agent_brain

    choice = ModelChoice(
        "deepseek", "deepseek-chat", "DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        catalog_id="deepseek-v3",
    )
    with patch.object(agent_brain, "_call_openai_compat", return_value='{"tool":"finish"}') as m:
        agent_brain._dispatch_catalog_provider("deepseek", "s", "u", choice)
        assert m.called
        # model id passed should be deepseek-chat (v3), not flash
        assert m.call_args[0][2] == "deepseek-chat"


def test_dispatch_openai_gpt4o_mini():
    _clear()
    os.environ["OPENAI_API_KEY"] = "sk-oai"
    from lumen.engine.services.cline_runtime.model_router import ModelChoice
    from lumen.engine.services.cline_runtime import agent_brain

    choice = ModelChoice(
        "openai", "gpt-4o-mini", "OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        catalog_id="openai-gpt-4o-mini",
    )
    with patch.object(agent_brain, "_call_openai_compat", return_value='{"tool":"finish"}') as m:
        agent_brain._invoke_choice(choice, "sys", "user")
        assert m.called
        assert m.call_args[0][2] == "gpt-4o-mini"
        assert "api.openai.com" in (m.call_args[1].get("base_url") or m.call_args.kwargs.get("base_url") or "")


def test_dispatch_anthropic_native():
    _clear()
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    from lumen.engine.services.cline_runtime.model_router import ModelChoice
    from lumen.engine.services.cline_runtime import agent_brain

    choice = ModelChoice(
        "anthropic", "claude-3-haiku-20240307", "ANTHROPIC_API_KEY",
        catalog_id="claude-3-haiku",
    )
    with patch.object(agent_brain, "_call_anthropic", return_value='{"tool":"finish"}') as m:
        agent_brain._dispatch_catalog_provider("anthropic", "s", "u", choice)
        assert m.called
        assert "haiku" in m.call_args[0][2]


def test_openai_compat_records_usage():
    _clear()
    from lumen.engine.services.cline_runtime import agent_brain
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "choices": [{"message": {"content": '{"tool":"finish"}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    with patch("requests.post", return_value=fake):
        agent_brain._LAST_CALL_USAGE.clear() if hasattr(agent_brain._LAST_CALL_USAGE, "clear") else None
        text = agent_brain._call_openai_compat(
            "s", "u", "gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key="sk-x",
        )
        assert "finish" in text
        usage = agent_brain.get_last_call_usage()
        assert usage.get("total_tokens") == 5 or usage.get("model_id") == "gpt-4o-mini"


def test_gemini_does_not_try_stale_models_first():
    import inspect
    from lumen.engine.services.cline_runtime import agent_brain
    src = inspect.getsource(agent_brain._call_gemini)
    assert "gemini-3.1-flash-lite" not in src
    assert "gemini_model_id_missing" in src


def test_all_plan_providers_have_invoke_path():
    """Every catalog provider used in plan must be handled by _invoke_choice."""
    from lumen.engine.services.llm.model_catalog import CATALOG
    from lumen.engine.services.cline_runtime import agent_brain
    import inspect
    src = inspect.getsource(agent_brain._invoke_choice)
    for m in CATALOG:
        if m.provider in {"foundry", "openai", "openrouter", "deepseek", "anthropic", "gemini", "groq"}:
            assert m.provider in src or "_dispatch_catalog_provider" in src


def test_plan_with_only_deepseek_picks_v3_not_pro():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.llm.r2_allocator import allocate
    from lumen.engine.services.cline_runtime.model_router import select_model
    r = allocate(task="plan", goal="architect full store bot")
    assert r is not None
    assert r.catalog_id == "deepseek-v3", r
    assert r.model_id == "deepseek-chat", r
    c = select_model(task="plan")
    assert c.catalog_id == "deepseek-v3" or c.model_id == "deepseek-chat"
    assert "v4-pro" not in (c.model_id or "")


def test_v4_pro_not_in_role_pool():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    from lumen.engine.services.llm.model_catalog import available_models, get_model
    pro = get_model("deepseek-v4-pro")
    assert pro is not None
    assert pro.roles == () or "plan" not in pro.roles
    ids = {m.id for m in available_models(role="plan")}
    assert "deepseek-v4-pro" not in ids
    assert "deepseek-v3" in ids
