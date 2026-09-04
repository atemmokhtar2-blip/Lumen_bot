
"""Phase 1: unified model catalog completeness vs product plan."""
import os


def _clear():
    for k in (
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
        "AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT", "DEEPSEEK_MODEL",
        "DEEPSEEK_V3_MODEL", "DEEPSEEK_FLASH_MODEL", "DEEPSEEK_PRO_MODEL",
    ):
        os.environ.pop(k, None)


def test_plan_required_ids_present():
    from lumen.engine.services.llm.model_catalog import (
        assert_plan_catalog_complete, PLAN_REQUIRED_IDS, get_model,
    )
    missing = assert_plan_catalog_complete()
    assert missing == [], missing
    for cid in PLAN_REQUIRED_IDS:
        m = get_model(cid)
        assert m is not None, cid
        assert m.provider
        assert m.model_id
        assert m.roles
        assert m.api_style in {"openai_compat", "gemini", "anthropic"}


def test_deepseek_v4_flash_official_id():
    from lumen.engine.services.llm.model_catalog import get_model
    m = get_model("deepseek-v4-flash")
    assert m.provider == "deepseek"
    assert m.model_id == "deepseek-v4-flash"
    assert m.api_key_env == "DEEPSEEK_API_KEY"
    assert "build" in m.roles


def test_deepseek_v3_is_chat_id():
    _clear()
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    m = mc.get_model("deepseek-v3")
    assert m is not None
    assert m.model_id == "deepseek-chat", m.model_id
    assert "plan" in m.roles


def test_gemini_pro_and_flash_lite():
    from lumen.engine.services.llm.model_catalog import get_model
    assert get_model("gemini-2.5-flash-lite").model_id == "gemini-2.5-flash-lite"
    assert get_model("gemini-2.5-pro").model_id == "gemini-2.5-pro"


def test_openai_gpt4o_mini_and_claude_haiku():
    from lumen.engine.services.llm.model_catalog import get_model
    assert get_model("openai-gpt-4o-mini").model_id == "gpt-4o-mini"
    assert "haiku" in get_model("claude-3-haiku").model_id


def test_openrouter_and_foundry_and_groq():
    from lumen.engine.services.llm.model_catalog import get_model
    assert get_model("openrouter-auto").provider == "openrouter"
    assert get_model("foundry-model-router").model_id == "model-router"
    assert get_model("groq-fast").provider == "groq"


def test_without_key_excluded_from_pool():
    _clear()
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    assert mc.available_models() == []


def test_with_key_included():
    _clear()
    os.environ["OPENAI_API_KEY"] = "sk-test"
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    ids = {m.id for m in mc.available_models()}
    assert "openai-gpt-4o-mini" in ids
    assert "deepseek-v4-flash" not in ids  # no deepseek key


def test_openrouter_key_rewrites_deepseek_dispatch():
    _clear()
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
    from importlib import reload
    import lumen.engine.services.llm.model_catalog as mc
    reload(mc)
    m = mc.get_model("deepseek-v4-flash")
    assert m.key_present()
    d = m.resolve_dispatch()
    assert d["provider"] == "openrouter"
    assert d["model_id"].startswith("deepseek/")
    assert "openrouter.ai" in d["base_url"]


def test_catalog_snapshot_fields():
    from lumen.engine.services.llm.model_catalog import catalog_snapshot
    rows = catalog_snapshot()
    assert len(rows) >= 9
    row = next(r for r in rows if r["id"] == "deepseek-v4-flash")
    for k in ("provider", "model_id", "roles", "cost_tier", "strength", "key_present"):
        assert k in row
