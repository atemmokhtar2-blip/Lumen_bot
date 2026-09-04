
"""Phase 3b: R2-style allocator + Foundry-first selection."""
from __future__ import annotations

import os


def _clear():
    for k in (
        "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY",
        "GEMINI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
        "AZURE_FOUNDRY_KEY", "AZURE_FOUNDRY_ENDPOINT", "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT", "CLINE_LLM_PROVIDER", "CLINE_ROUTER",
    ):
        os.environ.pop(k, None)


def test_decompose_kinds():
    from lumen.engine.services.llm.r2_allocator import decompose_step
    assert decompose_step(task="plan") == "plan"
    assert decompose_step(task="critique") == "critique"
    assert decompose_step(task="repair") == "repair"
    assert decompose_step(task="build", findings_count=4) == "repair"
    assert decompose_step(task="build", goal="implement echo bot") == "code"


def test_allocate_picks_available():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.llm.r2_allocator import allocate
    r = allocate(task="build", goal="write bot code")
    assert r is not None
    assert r.provider == "deepseek"
    assert r.step_kind == "code"
    assert r.score > 0


def test_allocate_plan_prefers_stronger():
    _clear()
    os.environ["DEEPSEEK_API_KEY"] = "sk-ds"
    os.environ["OPENAI_API_KEY"] = "sk-oai"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.llm.r2_allocator import allocate
    r = allocate(task="plan", goal="architect full store bot")
    assert r is not None
    assert r.step_kind == "plan"
    # deepseek-v3 preferred for plan over flash
    assert "pro" in r.model_id or "v4-pro" in r.model_id or r.model_id == "deepseek-v4-pro"


def test_select_model_for_goal_foundry_first():
    _clear()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://ex.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "k"
    os.environ["CLINE_ROUTER"] = "auto"
    from lumen.engine.services.cline_runtime.model_router import select_model_for_goal
    choice, meta = select_model_for_goal(task="build", goal="x")
    assert choice.provider == "foundry"
    assert meta["router"] == "foundry"


def test_select_model_for_goal_local_allocator():
    _clear()
    os.environ["OPENAI_API_KEY"] = "sk-oai"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.cline_runtime.model_router import select_model_for_goal
    choice, meta = select_model_for_goal(task="build", goal="code a bot")
    assert choice.provider == "openai"
    assert meta["router"] == "r2_allocator"
    assert "band" in meta
    assert meta.get("step_kind") == "code"


def test_cline_router_foundry_forced():
    _clear()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://ex.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "k"
    os.environ["OPENAI_API_KEY"] = "sk-oai"
    os.environ["CLINE_ROUTER"] = "foundry"
    from lumen.engine.services.cline_runtime.model_router import select_model
    assert select_model(task="build").provider == "foundry"


def test_cline_router_local_skips_foundry():
    _clear()
    os.environ["AZURE_FOUNDRY_ENDPOINT"] = "https://ex.openai.azure.com"
    os.environ["AZURE_FOUNDRY_KEY"] = "k"
    os.environ["OPENAI_API_KEY"] = "sk-oai"
    os.environ["CLINE_ROUTER"] = "local"
    from lumen.engine.services.cline_runtime.model_router import select_model_for_goal
    choice, meta = select_model_for_goal(task="build", goal="hi")
    assert choice.provider == "openai"
    assert meta["router"] == "r2_allocator"
