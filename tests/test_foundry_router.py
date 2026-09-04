
"""Phase 3: Microsoft Foundry Model Router — production primary (real wiring)."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


def _clear_llm_keys():
    for k in (
        "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY",
        "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY", "CLINE_LLM_PROVIDER",
        "AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT",
        "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
        "AZURE_FOUNDRY_DEPLOYMENT", "AZURE_FOUNDRY_DEPLOYMENT_QUALITY",
        "AZURE_FOUNDRY_DEPLOYMENT_COST", "AZURE_FOUNDRY_DEPLOYMENT_BALANCED",
        "AZURE_OPENAI_DEPLOYMENT", "AZURE_FOUNDRY_ROUTING_MODE", "CLINE_ROUTER",
    ):
        os.environ.pop(k, None)


def test_foundry_preferred_when_configured():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="build")
    assert c.provider == "foundry"
    assert c.model_id  # deployment name
    assert c.key_present()
    c2 = select_model(task="plan")
    assert c2.provider == "foundry"


def test_mode_and_deployment_mapping():
    _clear_llm_keys()
    from lumen.engine.services.llm.foundry_router import mode_for_task, deployment_for_mode
    assert mode_for_task("plan") == "quality"
    assert mode_for_task("critique") == "quality"
    assert mode_for_task("build") == "cost"
    os.environ["AZURE_FOUNDRY_DEPLOYMENT_QUALITY"] = "router-quality"
    os.environ["AZURE_FOUNDRY_DEPLOYMENT_COST"] = "router-cost"
    assert deployment_for_mode("quality") == "router-quality"
    assert deployment_for_mode("cost") == "router-cost"


def test_select_model_uses_mode_deployments():
    _clear_llm_keys()
    os.environ.pop("AZURE_FOUNDRY_DEPLOYMENT", None)
    os.environ.pop("AZURE_OPENAI_DEPLOYMENT", None)
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    os.environ["AZURE_FOUNDRY_DEPLOYMENT_QUALITY"] = "router-quality"
    os.environ["AZURE_FOUNDRY_DEPLOYMENT_COST"] = "router-cost"
    from lumen.engine.services.cline_runtime.model_router import select_model
    assert select_model(task="plan").model_id == "router-quality"
    assert select_model(task="build").model_id == "router-cost"


def test_chat_completions_azure_deployment_url():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.llm import foundry_router

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"tool":"finish"}'}}],
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    with patch("requests.post", return_value=mock_resp) as post:
        out = foundry_router.chat_completions(
            system="s", user="u", task="build", deployment="model-router"
        )
        assert out["content"]
        assert out["model"] == "gpt-4o-mini"
        assert out["mode"] == "cost"
        assert out["usage"]["prompt_tokens"] == 10
        url = post.call_args[0][0]
        assert "/openai/deployments/model-router/chat/completions" in url
        assert "api-version=" in url
        assert post.call_args[1]["headers"].get("api-key") == "azure-key-test"
        last = foundry_router.get_last_result()
        assert last.get("model") == "gpt-4o-mini"


def test_chat_completions_fallback_urls():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.llm import foundry_router

    fail = MagicMock()
    fail.status_code = 404
    fail.text = "not found"
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "model": "deepseek-v3",
    }
    with patch("requests.post", side_effect=[fail, ok]) as post:
        out = foundry_router.chat_completions(system="s", user="u", task="plan")
        assert out["content"] == "ok"
        assert post.call_count == 2
        assert "/openai/v1/chat/completions" in post.call_args_list[1][0][0]


def test_invoke_foundry_injects_json_schema():
    from unittest.mock import patch
    from lumen.engine.services.cline_runtime.model_router import ModelChoice
    from lumen.engine.services.cline_runtime import agent_brain

    choice = ModelChoice(
        "foundry", "model-router", "AZURE_FOUNDRY_KEY",
        base_url="https://example.openai.azure.com",
    )
    with patch(
        "lumen.engine.services.llm.foundry_router.chat_completions",
        return_value={"content": '{"tool":"finish"}', "model": "gpt-4o-mini", "mode": "cost", "usage": {}},
    ) as m:
        agent_brain._invoke_choice(choice, "sys", "user-msg", task="build")
        kwargs = m.call_args.kwargs
        assert "JSON" in kwargs["user"] or "tool" in kwargs["user"]
        assert kwargs["deployment"] == "model-router"
        assert "CRITICAL" in kwargs["system"] or "sys" in kwargs["system"]


def test_decide_passes_task_to_foundry():
    import inspect
    from lumen.engine.services.cline_runtime import agent_brain
    src = inspect.getsource(agent_brain.decide)
    assert "task: str" in src
    assert "_invoke_choice(choice, system, user, task=task)" in src


def test_agent_loop_passes_task():
    import inspect
    from lumen.engine.services.cline_runtime import agent_loop
    src = inspect.getsource(agent_loop)
    assert "task=task" in src


def test_forced_non_foundry_still_works():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    os.environ["OPENAI_API_KEY"] = "sk-openai"
    os.environ["CLINE_LLM_PROVIDER"] = "openai"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="build")
    assert c.provider == "openai"


def test_describe_runtime_foundry_block():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.cline_runtime.model_router import describe_runtime
    d = describe_runtime()
    assert d["provider"] == "foundry"
    assert d["foundry"]["configured"] is True
    assert d["foundry"]["primary"] is True
