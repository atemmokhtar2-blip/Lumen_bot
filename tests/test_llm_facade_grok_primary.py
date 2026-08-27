"""Chat prefers Grok; strict Gemini/Groq role split is off by default."""


def test_strict_roles_default_off(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    from lumen.engine.services.llm.facade import _strict_llm_roles

    assert _strict_llm_roles() is False


def test_chat_prefers_xai_when_keyed(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.delenv("CHAT_PROVIDER", raising=False)
    from lumen.engine.services.llm.facade import get_chat_provider_name, _chat_chain

    assert get_chat_provider_name() == "xai"
    assert [p.name for p in _chat_chain()][0] == "xai"


def test_translate_not_forced_gemini(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    monkeypatch.delenv("TRANSLATE_PROVIDER", raising=False)
    from lumen.engine.services.llm.facade import get_translate_provider_name

    assert get_translate_provider_name() != "gemini" or True
    assert get_translate_provider_name() == "groq"


def test_model_router_xai_first_for_build(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.delenv("CLINE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ENGINE_LLM_PROVIDER", raising=False)
    from lumen.engine.services.cline_runtime.model_router import select_model

    c = select_model(task="build")
    assert c.provider == "xai"
