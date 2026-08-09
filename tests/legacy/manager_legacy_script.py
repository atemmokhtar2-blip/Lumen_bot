"""
Test script for the Core Engine Manager (Specification 003).

Exercises:
  1. Registration with unique IDs and metadata.
  2. Duplicate ID rejection.
  3. Lifecycle enforcement (no skipping).
  4. Dependency validation (unregistered + unmet).
  5. Security rules (unregistered, non-Ready, self-start).
  6. Error management (engine failure stops the pipeline).
  7. Execution queue ordering.
  8. Full managed run with happy path.
  9. Full managed run with a failing engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.core.contracts import Engine
from telegram_bot_engine.core.result import StageResult
from telegram_bot_engine.manager import (
    CoreEngineManager,
    DependencyError,
    DuplicateEngineError,
    EngineState,
    LifecycleError,
    ManagerError,
    SecurityError,
    UnknownEngineError,
)
from telegram_bot_engine.manager.lifecycle import EngineStateTransition


# ---------------------------------------------------------------------------
# Minimal fake engine for testing
# ---------------------------------------------------------------------------

class FakeEngine(Engine):
    """A controllable fake engine for manager tests."""

    def __init__(self, name: str, version: str = "1.0.0",
                 should_fail: bool = False,
                 init_fails: bool = False,
                 fail_message: str = "forced failure"):
        # Component fields
        self.name = name
        self.version = version
        self.description = f"Fake engine {name}"
        self.tags: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self._should_fail = should_fail
        self._init_fails = init_fails
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
        if self._init_fails:
            raise RuntimeError("init failure")
        self.was_initialized = True


def _make_context() -> GenerationContext:
    from pathlib import Path
    return GenerationContext(
        request="test request",
        config=None,
        work_dir=Path("/tmp/tbe_test"),
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# ---------------------------------------------------------------------------
# Test 1: Registration with unique IDs and metadata
# ---------------------------------------------------------------------------
section("Test 1: Registration with unique IDs and metadata")
mgr = CoreEngineManager()
e1 = FakeEngine("engine_one")
e2 = FakeEngine("engine_two")
entry1 = mgr.register(e1, engine_id="e1", priority=10, dependencies=[])
entry2 = mgr.register(e2, engine_id="e2", priority=20, dependencies=["e1"])
check("count is 2", mgr.count() == 2, str(mgr.count()))
check("e1 entry name", mgr.get("e1").name == "engine_one")
check("e1 entry priority", mgr.get("e1").priority == 10)
check("e1 status registered", mgr.get("e1").status == EngineState.REGISTERED)
check("e2 dependencies", mgr.get("e2").dependencies == {"e1"})
check("enabled by default", mgr.get("e1").enabled is True)


# ---------------------------------------------------------------------------
# Test 2: Duplicate ID rejection
# ---------------------------------------------------------------------------
section("Test 2: Duplicate ID rejection")
try:
    mgr.register(FakeEngine("dup"), engine_id="e1")
    check("duplicate rejected", False, "no exception raised")
except DuplicateEngineError:
    check("duplicate rejected", True)
except Exception as exc:
    check("duplicate rejected", False, f"wrong exception: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Test 3: Lifecycle enforcement (no skipping)
# ---------------------------------------------------------------------------
section("Test 3: Lifecycle enforcement (no skipping)")
mgr2 = CoreEngineManager()
engine_a = FakeEngine("alpha")
mgr2.register(engine_a, engine_id="alpha", priority=1)

# Try to run without loading / initializing / marking ready.
try:
    mgr2.run_engine("alpha", _make_context())
    check("cannot run from Registered", False, "no exception")
except SecurityError:
    check("cannot run from Registered (SecurityError)", True)
except Exception as exc:
    check("cannot run from Registered", False, f"wrong exc: {type(exc).__name__}")

# Load, then try to skip to Running (skip initialize + ready).
mgr2.load("alpha")
check("alpha loaded", mgr2.get("alpha").status == EngineState.LOADED)

# Try to mark_ready before initialize — illegal transition.
try:
    mgr2.mark_ready("alpha")
    check("cannot skip initialize", False, "no exception")
except LifecycleError:
    check("cannot skip initialize (LifecycleError)", True)
except Exception as exc:
    check("cannot skip initialize", False, f"wrong exc: {type(exc).__name__}")

# Proper path: load → initialize → mark_ready.
mgr2.initialize("alpha")
check("alpha initialized", mgr2.get("alpha").status == EngineState.INITIALIZED)
check("alpha.initialize() called", engine_a.was_initialized)
mgr2.mark_ready("alpha")
check("alpha ready", mgr2.get("alpha").status == EngineState.READY)


# ---------------------------------------------------------------------------
# Test 4: Dependency validation
# ---------------------------------------------------------------------------
section("Test 4: Dependency validation")
mgr3 = CoreEngineManager()
ea = FakeEngine("a")
eb = FakeEngine("b")
mgr3.register(ea, engine_id="a", priority=1)
mgr3.register(eb, engine_id="b", priority=2, dependencies=["a"])

# Bring a to ready and run it.
mgr3.load("a")
mgr3.initialize("a")
mgr3.mark_ready("a")
mgr3.run_engine("a", _make_context())
check("a completed", mgr3.get("a").status == EngineState.COMPLETED)

# Now b's dependency (a) is completed.  Bring b to ready.
mgr3.load("b")
mgr3.initialize("b")
mgr3.mark_ready("b")
result_b = mgr3.run_engine("b", _make_context())
check("b completed after a", mgr3.get("b").status == EngineState.COMPLETED)
check("b result success", result_b.success)

# Test unregistered dependency.
mgr4 = CoreEngineManager()
ec = FakeEngine("c")
mgr4.register(ec, engine_id="c", priority=1, dependencies=["nonexistent"])
mgr4.load("c")
mgr4.initialize("c")
mgr4.mark_ready("c")
try:
    mgr4.run_engine("c", _make_context())
    check("unregistered dependency detected", False, "no exception")
except DependencyError:
    check("unregistered dependency detected (DependencyError)", True)
except Exception as exc:
    check("unregistered dependency detected", False,
          f"wrong exc: {type(exc).__name__}")

# Test unmet dependency (dependency registered but not completed).
mgr5 = CoreEngineManager()
ed = FakeEngine("d")
ee = FakeEngine("e")
mgr5.register(ed, engine_id="d", priority=1)
mgr5.register(ee, engine_id="e", priority=2, dependencies=["d"])
mgr5.load("d")
mgr5.initialize("d")
mgr5.mark_ready("d")
mgr5.load("e")
mgr5.initialize("e")
mgr5.mark_ready("e")
# Don't run d yet — try to run e first.
try:
    mgr5.run_engine("e", _make_context())
    check("unmet dependency detected", False, "no exception")
except DependencyError:
    check("unmet dependency detected (DependencyError)", True)
except Exception as exc:
    check("unmet dependency detected", False,
          f"wrong exc: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Test 5: Security rules
# ---------------------------------------------------------------------------
section("Test 5: Security rules")
mgr6 = CoreEngineManager()

# Unregistered engine.
try:
    mgr6.run_engine("ghost", _make_context())
    check("unregistered engine blocked", False, "no exception")
except SecurityError as exc:
    check("unregistered engine blocked (SecurityError)", True,
          f"rule={exc.rule}")
except Exception as exc:
    check("unregistered engine blocked", False,
          f"wrong exc: {type(exc).__name__}")

# Unknown engine lookup.
try:
    mgr6.get_or_raise("nonexistent")
    check("unknown engine raises", False)
except UnknownEngineError:
    check("unknown engine raises (UnknownEngineError)", True)
except Exception as exc:
    check("unknown engine raises", False, f"wrong exc: {type(exc).__name__}")

# Disabled engine cannot run.
mgr6b = CoreEngineManager()
ef = FakeEngine("f")
mgr6b.register(ef, engine_id="f", priority=1, enabled=False)
try:
    mgr6b.run_engine("f", _make_context())
    check("disabled engine blocked", False, "no exception")
except SecurityError as exc:
    check("disabled engine blocked (SecurityError)", True,
          f"rule={exc.rule}")
except Exception as exc:
    check("disabled engine blocked", False, f"wrong exc: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Test 6: Error management — engine failure stops the pipeline
# ---------------------------------------------------------------------------
section("Test 6: Error management (engine failure stops pipeline)")
mgr7 = CoreEngineManager()
eg = FakeEngine("g")
eh = FakeEngine("h", should_fail=True, fail_message="boom")
ei = FakeEngine("i")
mgr7.register(eg, engine_id="g", priority=1)
mgr7.register(eh, engine_id="h", priority=2, dependencies=["g"])
mgr7.register(ei, engine_id="i", priority=3, dependencies=["h"])

result = mgr7.run_all(_make_context())
check("run_all not success", result.success is False)
check("failed engine is h", result.failed_engine_id == "h",
      str(result.failed_engine_id))
check("h is Failed state", mgr7.get("h").status == EngineState.FAILED)
check("i never ran", mgr7.get("i").status != EngineState.COMPLETED)
check("i still Registered or not running",
      mgr7.get("i").status in (EngineState.REGISTERED, EngineState.READY,
                               EngineState.LOADED, EngineState.INITIALIZED),
      str(mgr7.get("i").status))
check("errors recorded", len(result.errors) > 0)
check("g completed", mgr7.get("g").status == EngineState.COMPLETED)


# ---------------------------------------------------------------------------
# Test 7: Execution queue ordering (priority + dependencies)
# ---------------------------------------------------------------------------
section("Test 7: Execution queue ordering")
mgr8 = CoreEngineManager()
ej = FakeEngine("j")
ek = FakeEngine("k")
el = FakeEngine("l")
em = FakeEngine("m")
# m depends on l; l depends on k; j is independent, lowest priority.
mgr8.register(ej, engine_id="j", priority=50)
mgr8.register(ek, engine_id="k", priority=10)
mgr8.register(el, engine_id="l", priority=20, dependencies=["k"])
mgr8.register(em, engine_id="m", priority=5, dependencies=["l"])

order = [q.engine_id for q in mgr8.queue_order()]
check("queue respects dependencies", order.index("k") < order.index("l"),
      str(order))
check("queue respects dependencies 2", order.index("l") < order.index("m"),
      str(order))
check("k runs before j (priority)", order.index("k") < order.index("j"),
      str(order))


# ---------------------------------------------------------------------------
# Test 8: Full managed run — happy path
# ---------------------------------------------------------------------------
section("Test 8: Full managed run (happy path)")
mgr9 = CoreEngineManager()
en = FakeEngine("n")
eo = FakeEngine("o")
ep = FakeEngine("p")
mgr9.register(en, engine_id="n", priority=1)
mgr9.register(eo, engine_id="o", priority=2, dependencies=["n"])
mgr9.register(ep, engine_id="p", priority=3, dependencies=["n", "o"])

result = mgr9.run_all(_make_context())
check("happy path success", result.success, str(result.errors))
check("all 3 engines ran", len(result.engine_results) == 3,
      str(len(result.engine_results)))
check("n completed", mgr9.get("n").status == EngineState.COMPLETED)
check("o completed", mgr9.get("o").status == EngineState.COMPLETED)
check("p completed", mgr9.get("p").status == EngineState.COMPLETED)
check("n initialized", en.was_initialized)
check("o initialized", eo.was_initialized)
check("p initialized", ep.was_initialized)
check("total duration recorded", result.total_duration_s >= 0)


# ---------------------------------------------------------------------------
# Test 9: Lifecycle transition table correctness
# ---------------------------------------------------------------------------
section("Test 9: Lifecycle transition table")
check("REGISTERED→LOADED valid",
      EngineStateTransition.is_valid(EngineState.REGISTERED,
                                      EngineState.LOADED))
check("REGISTERED→RUNNING invalid (skip)",
      not EngineStateTransition.is_valid(EngineState.REGISTERED,
                                          EngineState.RUNNING))
check("LOADED→READY invalid (skip)",
      not EngineStateTransition.is_valid(EngineState.LOADED,
                                          EngineState.READY))
check("COMPLETED→READY valid (reset)",
      EngineStateTransition.is_valid(EngineState.COMPLETED,
                                      EngineState.READY))
check("FAILED is terminal",
      EngineStateTransition.is_terminal(EngineState.FAILED))
check("COMPLETED not terminal",
      not EngineStateTransition.is_terminal(EngineState.COMPLETED))
check("RUNNING→COMPLETED valid",
      EngineStateTransition.is_valid(EngineState.RUNNING,
                                      EngineState.COMPLETED))
check("RUNNING→FAILED valid",
      EngineStateTransition.is_valid(EngineState.RUNNING,
                                      EngineState.FAILED))
check("FAILED→anything invalid",
      not EngineStateTransition.is_valid(EngineState.FAILED,
                                          EngineState.READY))


# ---------------------------------------------------------------------------
# Test 10: Bootstrap integration — manager is returned
# ---------------------------------------------------------------------------
section("Test 10: Bootstrap integration")
from telegram_bot_engine.core.bootstrap import bootstrap
boot = bootstrap()
check("bootstrap returns 3-tuple", len(boot) == 3, str(len(boot)))
registry, orchestrator, manager = boot
check("manager is CoreEngineManager",
      isinstance(manager, CoreEngineManager))
check("manager has 14 engines", manager.count() == 14,
      str(manager.count()))
states = manager.states()
check("all engines Registered initially",
      all(s == EngineState.REGISTERED.value for s in states.values()),
      str(states))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"RESULTS: {passed} passed, {failed} failed")
print(f"{'=' * 60}")
if failed > 0:
    raise SystemExit(1)
