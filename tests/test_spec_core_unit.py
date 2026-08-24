"""Unit tests for spec_core — registry, integrity, durable workflow."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_capabilities_registry_non_empty():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    assert isinstance(CAPABILITIES, dict)
    assert len(CAPABILITIES) >= 50


def test_capability_keys_unique_and_stable():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    keys = list(CAPABILITIES.keys())
    assert len(keys) == len(set(keys))
    for key in keys:
        assert isinstance(key, str)
        assert key.strip() == key
        assert " " not in key


def test_start_help_capabilities_present():
    from telegram_bot_engine.spec_core.registry import CAPABILITIES

    keys = set(CAPABILITIES.keys())
    assert "start" in keys
    assert "help" in keys


def test_builder_import_and_surface():
    from telegram_bot_engine.spec_core import builder

    assert builder is not None
    # common builder entrypoints if present
    names = dir(builder)
    assert len(names) > 5


def test_acceptance_gate_importable():
    from telegram_bot_engine.spec_core import acceptance_gate

    assert acceptance_gate is not None


def test_capability_integrity_module():
    from telegram_bot_engine.spec_core import capability_integrity

    assert capability_integrity is not None


def test_durable_journal_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_WORKFLOW_JOURNAL_DIR", str(tmp_path / "journal"))
    from telegram_bot_engine.services.multi_agent.durable_workflow import (
        DurableWorkflowJournal,
        JournalEntry,
    )

    j = DurableWorkflowJournal(root=tmp_path / "journal")
    e = JournalEntry(
        workflow_id="wf_test123",
        state_id="st_1",
        step="architect",
        status="running",
        user_id=42,
        description="test bot",
    )
    j.write(e)
    loaded = j.get("wf_test123")
    assert loaded is not None
    assert loaded.step == "architect"
    assert j.get_by_state("st_1").workflow_id == "wf_test123"


def test_workflow_engine_memory_checkpoint():
    from telegram_bot_engine.services.multi_agent.workflow_engine import MemoryWorkflowEngine

    eng = MemoryWorkflowEngine()
    wid = eng.start("state_test_1", step="architect")
    eng.checkpoint(wid, state_id="state_test_1", step="builder", status="running")
    loaded = eng.resume(wid)
    assert loaded is not None
    assert loaded.step == "builder"


def test_prod_hard_locks_force_off_in_production(monkeypatch):
    from telegram_bot_engine.services import prod_hard_locks as ph

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_AUTO_HEAL_PIP", "1")
    monkeypatch.setenv("TBE_TOKEN_IN_ENV_FILE", "1")
    assert ph.auto_heal_pip_allowed() is False
    assert ph.token_in_env_file_allowed() is False


def test_isolation_policy_production_defaults(monkeypatch):
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.delenv("TBE_ALLOW_LOCAL_PROCESS", raising=False)
    from telegram_bot_engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.require_docker is True
    assert d.allow_local is False
