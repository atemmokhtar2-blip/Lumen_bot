from contextlib import nullcontext
"""Tests for fallback UX parity (weakness #3 root fix).

When the multi-agent orchestrator fails and the Cline fallback fires, the
user must see a clear message — not silence. The system must NOT look like
it is 'stuck' for minutes. This test verifies that run_generation tags the
result with metadata['fallback_used'] = 'cline' when the fallback path fires.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def _clean_env(monkeypatch):
    """Ensure orchestrator is enabled and no leftover env interferes."""
    monkeypatch.setenv("MULTI_AGENT_ORCHESTRATOR", "1")


def _mock_budget_ok(*a, **kw):
    """Bypass the LLM budget gate so tests reach the orchestrator path."""
    return True, "ok"


class TestFallbackUxParity:
    """The fallback must be visible to the user — tagged in result metadata."""

    def test_fallback_metadata_set_when_orchestrator_fails(self, _clean_env, monkeypatch):
        """When orchestrator_enabled() is True but orchestrate_generate fails with
        a fallbackable error, the Cline result must carry metadata['fallback_used']='cline'."""
        from lumen.engine.core.result import GenerationResult

        _failed_result = GenerationResult(
            success=False,
            errors=["langgraph_required: module not installed"],
            metadata={"stage": "orchestrate_generate"},
        )

        _cline_result = GenerationResult(
            success=True,
            project_path="/tmp/test_project",
            errors=[],
            metadata={"engine": "cline"},
        )

        import lumen.bot.helpers as helpers

        with nullcontext(), \
             patch("lumen.engine.services.multi_agent.orchestrate_generate", return_value=_failed_result), \
             patch("lumen.engine.services.multi_agent.orchestrator_enabled", return_value=True), \
             patch.object(helpers, "run_generation_with_bridge", return_value=_cline_result):

            result = helpers.run_generation(
                "test bot request",
                "/tmp/test_workdir",
                user_id=123,
            )

        meta = getattr(result, "metadata", None) or {}
        assert meta.get("fallback_used") == "cline", \
            f"Cline fallback result must be tagged with fallback_used='cline', got metadata={meta}"

    def test_no_fallback_metadata_when_orchestrator_succeeds(self, _clean_env, monkeypatch):
        """When the orchestrator succeeds directly, no fallback_used tag should appear."""
        from lumen.engine.core.result import GenerationResult

        _success_result = GenerationResult(
            success=True,
            project_path="/tmp/test_project",
            errors=[],
            metadata={"engine": "multi_agent"},
        )

        import lumen.bot.helpers as helpers

        with nullcontext(), \
             patch("lumen.engine.services.multi_agent.orchestrate_generate", return_value=_success_result), \
             patch("lumen.engine.services.multi_agent.orchestrator_enabled", return_value=True):

            result = helpers.run_generation(
                "test bot request",
                "/tmp/test_workdir",
                user_id=123,
            )

        meta = getattr(result, "metadata", None) or {}
        assert meta.get("fallback_used") is None, \
            f"Orchestrator success should NOT be tagged as fallback, got metadata={meta}"

    def test_fallback_metadata_when_orchestrator_raises_exception(self, _clean_env, monkeypatch):
        """When the orchestrator raises an exception (not just returns failure),
        the Cline fallback must still fire and be tagged."""
        from lumen.engine.core.result import GenerationResult

        _cline_result = GenerationResult(
            success=True,
            project_path="/tmp/test_project",
            errors=[],
            metadata={"engine": "cline"},
        )

        import lumen.bot.helpers as helpers

        def _raise(*a, **kw):
            raise RuntimeError("langgraph crashed")

        with nullcontext(), \
             patch("lumen.engine.services.multi_agent.orchestrate_generate", side_effect=_raise), \
             patch("lumen.engine.services.multi_agent.orchestrator_enabled", return_value=True), \
             patch.object(helpers, "run_generation_with_bridge", return_value=_cline_result):

            result = helpers.run_generation(
                "test bot request",
                "/tmp/test_workdir",
                user_id=123,
            )

        meta = getattr(result, "metadata", None) or {}
        assert meta.get("fallback_used") == "cline", \
            f"Exception fallback must be tagged, got metadata={meta}"

    def test_no_fallback_when_orchestrator_disabled(self, monkeypatch):
        """When orchestrator_enabled() is False, Cline runs as primary (not fallback)."""
        from lumen.engine.core.result import GenerationResult

        _cline_result = GenerationResult(
            success=True,
            project_path="/tmp/test_project",
            errors=[],
            metadata={"engine": "cline"},
        )

        monkeypatch.setenv("MULTI_AGENT_ORCHESTRATOR", "0")
        import lumen.bot.helpers as helpers

        with nullcontext(), \
             patch("lumen.engine.services.multi_agent.orchestrator_enabled", return_value=False), \
             patch.object(helpers, "run_generation_with_bridge", return_value=_cline_result):

            result = helpers.run_generation(
                "test bot request",
                "/tmp/test_workdir",
                user_id=123,
            )

        meta = getattr(result, "metadata", None) or {}
        assert meta.get("fallback_used") is None, \
            f"Cline as primary (orchestrator disabled) should NOT be tagged as fallback, got metadata={meta}"
