"""Unit tests for spec_core — registry, integrity, and basic composition."""
from __future__ import annotations

import pytest


def test_capabilities_registry_non_empty():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    assert isinstance(CAPABILITIES, dict)
    assert len(CAPABILITIES) >= 5
    for key, meta in list(CAPABILITIES.items())[:20]:
        assert isinstance(key, str) and key.strip()
        assert meta is not None


def test_capability_keys_are_stable_identifiers():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    for key in CAPABILITIES:
        assert key.replace("_", "").replace("-", "").isalnum() or "_" in key
        assert " " not in key


def test_start_and_help_exist():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    # core UX capabilities expected in production bots
    keys = set(CAPABILITIES.keys())
    assert "start" in keys or any("start" in k for k in keys)
    assert "help" in keys or any("help" in k for k in keys)


def test_builder_module_importable():
    from telegram_bot_engine.spec_core import builder

    assert hasattr(builder, "__file__") or builder is not None


def test_acceptance_gate_importable():
    from telegram_bot_engine.spec_core import acceptance_gate

    assert acceptance_gate is not None


def test_workflow_engine_memory_checkpoint():
    from telegram_bot_engine.services.multi_agent.workflow_engine import MemoryWorkflowEngine

    eng = MemoryWorkflowEngine()
    wid = eng.start("state_test_1", step="architect")
    cp = eng.checkpoint(wid, state_id="state_test_1", step="builder", status="running")
    assert cp.step == "builder"
    loaded = eng.resume(wid)
    assert loaded is not None
    assert loaded.state_id == "state_test_1"


def test_prod_hard_locks_production():
    import os
    from telegram_bot_engine.services import prod_hard_locks as ph

    old = os.environ.get("ENVIRONMENT")
    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["TBE_AUTO_HEAL_PIP"] = "1"
        os.environ["TBE_TOKEN_IN_ENV_FILE"] = "1"
        assert ph.auto_heal_pip_allowed() is False
        assert ph.token_in_env_file_allowed() is False
    finally:
        if old is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = old
        os.environ.pop("TBE_AUTO_HEAL_PIP", None)
        os.environ.pop("TBE_TOKEN_IN_ENV_FILE", None)
