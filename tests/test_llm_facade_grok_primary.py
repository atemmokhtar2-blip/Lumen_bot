"""Model catalog replaces retired llm.facade."""
from __future__ import annotations


def test_catalog_has_requested_models():
    from lumen.engine.services.llm.model_catalog import CATALOG

    ids = {m.id for m in CATALOG}
    assert "groq-deepseek-v4-flash" in ids
    assert "gemini-2.5-flash-lite" in ids
    assert "gemini-2.5-pro" in ids
    assert "openai-gpt-4o-mini" in ids
    assert "deepseek-v3" in ids
    assert "claude-3-haiku" in ids
    assert "openrouter-auto" in ids
    assert "foundry-model-router" in ids


def test_catalog_snapshot_safe():
    from lumen.engine.services.llm.model_catalog import catalog_snapshot

    rows = catalog_snapshot()
    assert isinstance(rows, list) and rows
    assert "key_present" in rows[0]
    assert "api_key" not in str(rows).lower() or "api_key_env" not in str(rows)


def test_no_facade_module():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert not (root / "lumen/engine/services/llm/facade.py").exists()
    assert not (root / "lumen/engine/services/llm_budget_gate.py").exists()
