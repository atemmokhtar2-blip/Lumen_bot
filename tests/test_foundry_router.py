
"""Phase 3: Microsoft Foundry Model Router production primary."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock


def _clear_llm_keys():
    for k in (
        "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY",
        "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY", "CLINE_LLM_PROVIDER",
    ):
        os.environ.pop(k, None)


def test_foundry_preferred_when_configured():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="build")
    assert c.provider == "foundry"
    assert c.key_present()
    c2 = select_model(task="plan")
    assert c2.provider == "foundry"


def test_mode_mapping():
    from lumen.engine.services.llm.foundry_router import mode_for_task
    assert mode_for_task("plan") == "quality"
    assert mode_for_task("critique") == "quality"
    assert mode_for_task("build") == "cost"


def test_chat_completions_azure_path():
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    from lumen.engine.services.llm import foundry_router

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "{\"tool\":\"finish\"}"}}],
        "model": "gpt-4o-mini",
        "usage": {},
    }
    with patch("requests.post", return_value=mock_resp) as post:
        out = foundry_router.chat_completions(
            system="s", user="u", task="build", deployment="model-router"
        )
        assert out["content"]
        assert out["model"] == "gpt-4o-mini"
        assert out["mode"] == "cost"
        url = post.call_args[0][0]
        assert "/openai/deployments/model-router/chat/completions" in url
        assert "api-version=" in url
        assert post.call_args[1]["headers"].get("api-key") == "azure-key-test"


def test_invoke_foundry_uses_router_client():
    from unittest.mock import patch
    from lumen.engine.services.cline_runtime.model_router import ModelChoice
    from lumen.engine.services.cline_runtime import agent_brain

    choice = ModelChoice(
        "foundry", "model-router", "AZURE_FOUNDRY_KEY",
        base_url="https://example.openai.azure.com",
    )
    with patch(
        "lumen.engine.services.llm.foundry_router.chat_completions",
        return_value={"content": "{\"tool\":\"finish\"}", "model": "gpt-4o-mini", "mode": "cost"},
    ) as m:
        text = agent_brain._invoke_choice(choice, "sys", "user", task="build")
        assert "finish" in text
        m.assert_called_once()
        assert m.call_args.kwargs.get("deployment") == "model-router"


def test_forced_non_foundry_still_works():
    _clear_llm_keys()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://example.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "azure-key-test"
    os.environ["OPENAI_API_KEY"] = "sk-openai"
    os.environ["CLINE_LLM_PROVIDER"] = "openai"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="build")
    assert c.provider == "openai"
