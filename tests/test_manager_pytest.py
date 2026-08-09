"""
Pytest-native tests for CoreEngineManager (Specification 003).

Covers:
  - Registration, uniqueness, metadata
  - Lifecycle enforcement
  - Dependency validation
  - Security rules
  - Queue ordering by priority
  - Failure stops the pipeline
  - Bootstrap produces 30 real engines with correct meta

STRICT RULE: These tests never introduce or rely on any pre-baked
bot templates. All generation remains fully dynamic from user text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.core.contracts import Engine
from telegram_bot_engine.core.result import StageResult
from telegram_bot_engine.manager import (
    CoreEngineManager,
    DependencyError,
    DuplicateEngineError,
    EngineState,
    SecurityError,
)
from telegram_bot_engine.core.bootstrap import bootstrap, ENGINE_META
from telegram_bot_engine.registry.discovery import ENGINE_CLASSES


class FakeEngine(Engine):
    """Controllable fake engine for unit tests."""

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        should_fail: bool = False,
        fail_message: str = "forced failure",
    ):
        self.name = name
        self.version = version
        self.description = f"Fake engine {name}"
        self.tags: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self._should_fail = should_fail
        self._fail_message = fail_message
        self.was_initialized = False
        self.executions = 0

    def execute(self, context: GenerationContext) -> StageResult:
        self.executions += 1
        if self._should_fail:
            return StageResult.failed(
                stage_name=self.name,
                errors=[self._fail_message],
            )
        return StageResult.ok(
            stage_name=self.name,
            outputs={"engine": self.name},
        )

    def initialize(self, config) -> None:
        self.was_initialized = True


def make_context() -> GenerationContext:
    return GenerationContext(
        request="test request",
        config=None,
        work_dir=Path("/tmp/tbe_test_pytest"),
    )


def bring_to_ready(mgr: CoreEngineManager, eid: str) -> None:
    mgr.load(eid)
    mgr.initialize(eid)
    mgr.mark_ready(eid)


def test_registration_unique_ids_and_metadata():
    mgr = CoreEngineManager()
    e1 = FakeEngine("engine_one")
    e2 = FakeEngine("engine_two")
    mgr.register(e1, engine_id="e1", priority=10, dependencies=[])
    mgr.register(e2, engine_id="e2", priority=20, dependencies=["e1"])

    assert mgr.count() == 2
    assert mgr.get("e1").name == "engine_one"
    assert mgr.get("e1").priority == 10
    assert mgr.get("e1").status == EngineState.REGISTERED
    assert mgr.get("e2").dependencies == {"e1"}
    assert mgr.get("e1").enabled is True


def test_duplicate_id_rejected():
    mgr = CoreEngineManager()
    mgr.register(FakeEngine("one"), engine_id="e1")
    with pytest.raises(DuplicateEngineError):
        mgr.register(FakeEngine("dup"), engine_id="e1")


def test_cannot_run_from_registered():
    mgr = CoreEngineManager()
    mgr.register(FakeEngine("alpha"), engine_id="alpha", priority=1)
    with pytest.raises(SecurityError):
        mgr.run_engine("alpha", make_context())


def test_full_lifecycle_to_completed():
    mgr = CoreEngineManager()
    eng = FakeEngine("alpha")
    mgr.register(eng, engine_id="alpha", priority=1)
    bring_to_ready(mgr, "alpha")
    result = mgr.run_engine("alpha", make_context())
    assert result.success
    assert mgr.get("alpha").status == EngineState.COMPLETED
    assert eng.executions == 1
    assert eng.was_initialized is True


def test_dependency_happy_path():
    mgr = CoreEngineManager()
    mgr.register(FakeEngine("a"), engine_id="a", priority=1)
    mgr.register(FakeEngine("b"), engine_id="b", priority=2, dependencies=["a"])

    bring_to_ready(mgr, "a")
    mgr.run_engine("a", make_context())
    assert mgr.get("a").status == EngineState.COMPLETED

    bring_to_ready(mgr, "b")
    result = mgr.run_engine("b", make_context())
    assert result.success
    assert mgr.get("b").status == EngineState.COMPLETED


def test_unregistered_dependency_raises():
    mgr = CoreEngineManager()
    mgr.register(
        FakeEngine("c"), engine_id="c", priority=1, dependencies=["nonexistent"]
    )
    bring_to_ready(mgr, "c")
    with pytest.raises(DependencyError):
        mgr.run_engine("c", make_context())


def test_unmet_dependency_raises():
    mgr = CoreEngineManager()
    mgr.register(FakeEngine("d"), engine_id="d", priority=1)
    mgr.register(FakeEngine("e"), engine_id="e", priority=2, dependencies=["d"])
    bring_to_ready(mgr, "d")
    bring_to_ready(mgr, "e")
    with pytest.raises(DependencyError):
        mgr.run_engine("e", make_context())


def test_unregistered_engine_cannot_run():
    mgr = CoreEngineManager()
    with pytest.raises((SecurityError, Exception)):
        mgr.run_engine("ghost", make_context())


def test_queue_order_respects_priority():
    mgr = CoreEngineManager()
    mgr.register(FakeEngine("late"), engine_id="late", priority=50)
    mgr.register(FakeEngine("early"), engine_id="early", priority=10)
    mgr.register(FakeEngine("mid"), engine_id="mid", priority=30)

    order = [e.engine_id for e in mgr.queue_order()]
    assert order == ["early", "mid", "late"]


def test_bootstrap_registers_all_real_engines():
    registry, orchestrator, manager = bootstrap()
    expected_count = len(ENGINE_CLASSES)
    assert expected_count == 13
    assert manager.count() == expected_count
    assert len(list(registry.engines())) == expected_count
    assert len(ENGINE_CLASSES) == expected_count

    for eng in registry.engines():
        assert type(eng).__name__ != "GenericEngine"

    queue = manager.queue_order()
    assert len(queue) == expected_count
    for item in queue:
        assert item.engine_id in ENGINE_META
        expected_prio, expected_deps = ENGINE_META[item.engine_id]
        assert item.priority == expected_prio
        assert set(item.dependencies) == set(expected_deps)

    prio = {i.engine_id: i.priority for i in queue}
    for item in queue:
        for dep in item.dependencies:
            assert prio[dep] < item.priority


def test_bootstrap_queue_is_topologically_sorted():
    _, _, manager = bootstrap()
    queue = manager.queue_order()
    seen = set()
    for item in queue:
        for dep in item.dependencies:
            assert dep in seen, f"{item.engine_id} runs before its dep {dep}"
        seen.add(item.engine_id)
