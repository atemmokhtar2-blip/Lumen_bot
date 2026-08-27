"""Temporal path smoke — no durable_workflow dependency."""
from __future__ import annotations

import pytest


def test_temporal_defs_import_without_journal():
    from lumen.engine.services.multi_agent import temporal_defs as td
    assert hasattr(td, "GenerateJobInput")
    # activities module loads even without temporalio installed
    assert td.GenerateJobInput is not None


def test_temporal_enabled_flag():
    from lumen.engine.services.multi_agent.event_wake import temporal_enabled
    assert isinstance(temporal_enabled(), bool)


def test_no_durable_workflow_module():
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lumen.engine.services.multi_agent.durable_workflow")
