
"""Phase 1 SoT: every choice path goes through catalog resolve_dispatch."""
import os


def _clear():
    for k in list(os.environ):
        if any(x in k for x in (
            "API_KEY", "FOUNDRY", "CLINE_", "ENGINE_LLM", "GEMINI", "GOOGLE",
            "DEEPSEEK", "OPENAI", "GROQ", "ANTHROPIC", "OPENROUTER", "AZURE",
        )):
            os.environ.pop(k, None)


def test_choice_from_catalog_sets_catalog_id():
    _clear()
    os.environ["OPENAI_API_KEY"] = "sk-x"
    from lumen.engine.services.llm.model_catalog import get_model
    from lumen.engine.services.cline_runtime.model_router import _choice_from_catalog_model
    m = get_model("openai-gpt-4o-mini")
    c = _choice_from_catalog_model(m)
    assert c.catalog_id == "openai-gpt-4o-mini"
    assert c.model_id == "gpt-4o-mini"
    assert c.provider == "openai"


def test_openrouter_only_rewrites_deepseek_choice():
    _clear()
    os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-test"
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    from lumen.engine.services.cline_runtime.model_router import _choice_from_catalog_model
    m = mc.get_model("deepseek-v4-flash")
    c = _choice_from_catalog_model(m)
    assert c.provider == "openrouter"
    assert c.model_id.startswith("deepseek/")
    assert c.catalog_id == "deepseek-v4-flash"
    assert "openrouter.ai" in (c.base_url or "")


def test_select_model_for_goal_attaches_catalog_id():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.cline_runtime.model_router import select_model_for_goal
    c, meta = select_model_for_goal(task="build", goal="write a telegram bot")
    assert c.provider != "none"
    assert meta.get("catalog_id") or c.catalog_id
    assert c.catalog_id or meta.get("catalog_id")


def test_cline_model_plan_override_uses_catalog_id():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["GOOGLE_API_KEY"] = "gk"
    os.environ["CLINE_ROUTER"] = "local"
    os.environ["CLINE_MODEL_PLAN"] = "gemini-2.5-pro"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="plan")
    assert c.catalog_id == "gemini-2.5-pro" or c.model_id == "gemini-2.5-pro"
    assert c.provider == "gemini"


def test_forced_deepseek_build_prefers_flash_role():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["CLINE_LLM_PROVIDER"] = "deepseek"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.cline_runtime.model_router import select_model
    c = select_model(task="build")
    assert c.provider in {"deepseek", "openrouter"}
    # role build → flash preferred over pro in ordered matches
    assert "flash" in c.model_id or c.catalog_id == "deepseek-v4-flash"
