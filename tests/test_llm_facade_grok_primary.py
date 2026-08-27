"""Chat prefers Groq (api.groq.com, NOT xAI); engine prefers Gemini; strict roles off."""


def test_strict_roles_default_off(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    from lumen.engine.services.llm.facade import _strict_llm_roles

    assert _strict_llm_roles() is False


def test_chat_prefers_groq_not_xai(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.delenv("CHAT_PROVIDER", raising=False)
    from lumen.engine.services.llm.facade import get_chat_provider_name, _chat_chain

    assert get_chat_provider_name() == "groq"
    names = [p.name for p in _chat_chain()]
    assert names[0] == "groq"
    # xai may appear later as optional fallback only
    if "xai" in names:
        assert names.index("xai") > names.index("groq")


def test_translate_not_forced_gemini(monkeypatch):
    monkeypatch.delenv("TBE_STRICT_LLM_ROLES", raising=False)
    monkeypatch.delenv("TRANSLATE_PROVIDER", raising=False)
    from lumen.engine.services.llm.facade import get_translate_provider_name

    assert get_translate_provider_name() == "groq"


def test_engine_build_order_gemini_before_groq():
    """Cline engine: Gemini leads for speed when both available."""
    import inspect
    from lumen.engine.services.cline_runtime import model_router as mr

    src = inspect.getsource(mr.select_model)
    # build branch order tuple must start with gemini
    assert 'order = ("gemini", "groq"' in src or "('gemini', 'groq'" in src
