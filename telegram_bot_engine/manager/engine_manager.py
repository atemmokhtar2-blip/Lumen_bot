"""
Core Engine Manager (Specification 003) — the executive brain.

The :class:`CoreEngineManager` is the sole authority over every engine
in the Telegram Bot Generation Engine.  It does **not** generate code,
create files, or analyse requests.  Its responsibilities, and only
these, are:

1. **Registration** — register every engine with a unique ID, name,
   version, status, priority, dependencies, and enabled flag.  No
   duplicate IDs are allowed.

2. **Lifecycle enforcement** — drive every engine through the states
   ``Registered → Loaded → Initialized → Ready → Running → Completed``
   (or ``Failed``).  No stage may be skipped.

3. **Dependency validation** — before running any engine, verify that
   all its declared dependencies have completed successfully.  If any
   dependency is missing or unmet, the engine does not run and the
   pipeline is stopped.

4. **Execution queue** — maintain an internal queue that determines the
   order in which engines run.  No engine can change its own order.

5. **Error management** — if any engine fails, stop the entire
   pipeline.  Log the failure reason, the engine name, and the stage
   where the error occurred.  No continuation is allowed.

6. **Logging** — log every operation: loading, starting, completing,
   failing, stopping, and the execution duration of each engine.

7. **Security** — enforce four rules:
     a. Unregistered engines cannot run.
     b. Engines not in the ``Ready`` state cannot run.
     c. Engines cannot start themselves directly.
     d. Engines cannot bypass the manager.

8. **Clear interfaces** — no engine accesses another engine directly.
   All communication flows through the manager.

9. **Future-ready** — the manager scales to hundreds of engines without
   redesign.  New engines can be added without modifying existing ones.

The manager is deliberately separate from the
:class:`~telegram_bot_engine.registry.EngineRegistry`.  The registry is
a dumb catalogue; the manager is the brain that enforces policy on top
of it.  The manager *uses* the registry for lookup but adds the
lifecycle, dependency, queue, security, and logging layers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from ..core.contracts import Engine
from ..core.context import GenerationContext
from ..core.result import StageResult
from ..logging import get_logger
from .engine_entry import EngineEntry, EngineMetadata
from .errors import (
    DependencyError,
    DuplicateEngineError,
    LifecycleError,
    ManagerError,
    SecurityError,
    UnknownEngineError,
)
from .execution_queue import ExecutionQueue, QueueItem
from .lifecycle import EngineState, EngineStateTransition

if TYPE_CHECKING:
    from ..configuration.config import Configuration

_logger = get_logger("manager")


# ---------------------------------------------------------------------------
# Manager-level result
# ---------------------------------------------------------------------------

@dataclass
class ManagerResult:
    """Outcome of a manager run (a full pipeline of managed engines).

    Attributes:
        success: ``True`` when every engine completed successfully.
        engine_results: Per-engine :class:`StageResult` objects, in
            execution order.
        errors: Aggregated list of error messages.
        failed_engine_id: The ID of the first engine that failed, if any.
        failure_stage: The lifecycle stage at which the failure occurred.
        total_duration_s: Total wall-clock duration of the managed run.
        metadata: Extra diagnostic information.
    """

    success: bool
    engine_results: List[StageResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    failed_engine_id: Optional[str] = None
    failure_stage: Optional[str] = None
    total_duration_s: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core Engine Manager
# ---------------------------------------------------------------------------

class CoreEngineManager:
    """The executive brain that manages every engine in the system.

    The manager is the *only* component that:

    * registers engines and assigns them management metadata,
    * transitions engines through their lifecycle,
    * validates dependencies before execution,
    * determines run order via the internal execution queue,
    * executes engines and collects their results,
    * stops the pipeline on the first failure,
    * logs every operation.

    Engines never call the manager's execution methods on themselves.
    They are passive participants: the manager drives them.
    """

    def __init__(self, config: "Optional[Configuration]" = None) -> None:
        self._config = config
        self._entries: Dict[str, EngineEntry] = {}
        self._queue: ExecutionQueue = ExecutionQueue()
        self._log = _logger
        self._failed: bool = False
        self._failed_engine_id: Optional[str] = None
        self._failure_stage: Optional[str] = None

    # -----------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------

    def register(
        self,
        engine: Engine,
        *,
        engine_id: str,
        priority: int = 100,
        dependencies: Optional[List[str]] = None,
        enabled: bool = True,
        metadata: Optional[EngineMetadata] = None,
    ) -> EngineEntry:
        """Register an engine with the manager.

        Parameters:
            engine: The :class:`~core.contracts.Engine` instance.
            engine_id: A unique, stable identifier for this engine.
            priority: Execution priority (lower runs first).
            dependencies: Engine IDs that must complete before this
                engine runs.
            enabled: Whether the engine is enabled.
            metadata: Optional :class:`EngineMetadata` for extra info.

        Returns:
            The created :class:`EngineEntry`.

        Raises:
            DuplicateEngineError: If *engine_id* is already registered.
        """
        if not engine_id:
            raise ValueError("engine_id must be a non-empty string.")

        if engine_id in self._entries:
            self._log.error(
                "Duplicate engine ID rejected",
                {"engine_id": engine_id, "stage": "register"},
            )
            raise DuplicateEngineError(engine_id)

        entry = EngineEntry(
            engine_id=engine_id,
            name=engine.name,
            version=engine.version,
            instance=engine,
            status=EngineState.REGISTERED,
            priority=priority,
            dependencies=set(dependencies or []),
            enabled=enabled,
            metadata=metadata,
        )

        self._entries[engine_id] = entry
        self._log.info(
            "Engine registered",
            {
                "engine_id": engine_id,
                "name": engine.name,
                "version": engine.version,
                "priority": priority,
                "dependencies": sorted(entry.dependencies),
                "enabled": enabled,
                "stage": "register",
            },
        )
        return entry

    # -----------------------------------------------------------------
    # Lookup
    # -----------------------------------------------------------------

    def get(self, engine_id: str) -> Optional[EngineEntry]:
        """Return the :class:`EngineEntry` for *engine_id*, or ``None``."""
        return self._entries.get(engine_id)

    def get_or_raise(self, engine_id: str) -> EngineEntry:
        """Return the entry for *engine_id* or raise :class:`UnknownEngineError`."""
        entry = self._entries.get(engine_id)
        if entry is None:
            raise UnknownEngineError(engine_id)
        return entry

    def all_entries(self) -> List[EngineEntry]:
        """Return all registered engine entries (insertion order)."""
        return list(self._entries.values())

    def enabled_entries(self) -> List[EngineEntry]:
        """Return all enabled engine entries."""
        return [e for e in self._entries.values() if e.enabled]

    def count(self) -> int:
        """Return the number of registered engines."""
        return len(self._entries)

    # -----------------------------------------------------------------
    # Lifecycle transitions (internal, but exposed for transparency)
    # -----------------------------------------------------------------

    def _transition(self, engine_id: str, target: EngineState,
                    stage_label: str) -> None:
        """Transition *engine_id* to *target*, enforcing lifecycle rules.

        Raises:
            UnknownEngineError: If the engine is not registered.
            LifecycleError: If the transition is illegal or would skip
                a stage.
        """
        entry = self.get_or_raise(engine_id)
        current = entry.status

        if not EngineStateTransition.is_valid(current, target):
            self._log.error(
                "Illegal lifecycle transition rejected",
                {
                    "engine_id": engine_id,
                    "current_state": current.value,
                    "attempted_state": target.value,
                    "stage": stage_label,
                },
            )
            raise LifecycleError(
                f"Cannot transition engine '{engine_id}' from "
                f"{current.value} to {target.value}.",
                engine_id=engine_id,
                current_state=current.value,
                attempted_state=target.value,
                stage=stage_label,
            )

        entry.status = target
        self._log.info(
            "Engine state transition",
            {
                "engine_id": engine_id,
                "from": current.value,
                "to": target.value,
                "stage": stage_label,
            },
        )

    # -- individual lifecycle steps ------------------------------------

    def load(self, engine_id: str) -> None:
        """Transition an engine from ``Registered`` to ``Loaded``.

        Raises:
            LifecycleError: If the engine is not in the ``Registered``
                state.
        """
        entry = self.get_or_raise(engine_id)
        if not entry.enabled:
            self._log.info(
                "Engine is disabled, skipping load",
                {"engine_id": engine_id, "stage": "load"},
            )
            return
        self._transition(engine_id, EngineState.LOADED, stage_label="load")

    def initialize(self, engine_id: str) -> None:
        """Initialize an engine: ``Loaded`` → ``Initialized``.

        Calls ``engine.initialize(config)`` and then transitions to
        ``Initialized``.  If initialization raises, the engine is
        marked ``Failed`` and the error is re-raised as a
        :class:`ManagerError`.
        """
        entry = self.get_or_raise(engine_id)
        if not entry.enabled:
            self._log.info(
                "Engine is disabled, skipping initialize",
                {"engine_id": engine_id, "stage": "initialize"},
            )
            return
        self._transition(engine_id, EngineState.INITIALIZED,
                         stage_label="initialize_pre")
        try:
            entry.instance.initialize(self._config)
        except Exception as exc:
            self._fail(engine_id, str(exc), stage="initialize")
            raise ManagerError(
                f"Engine '{engine_id}' failed during initialize: {exc}",
                engine_id=engine_id, stage="initialize",
            ) from exc
        self._log.info(
            "Engine initialized",
            {"engine_id": engine_id, "stage": "initialize"},
        )

    def mark_ready(self, engine_id: str) -> None:
        """Transition an engine from ``Initialized`` to ``Ready``."""
        entry = self.get_or_raise(engine_id)
        if not entry.enabled:
            return
        self._transition(engine_id, EngineState.READY, stage_label="ready")

    def reset(self, engine_id: str) -> None:
        """Reset a ``Completed`` engine back to ``Ready`` for a new run."""
        entry = self.get_or_raise(engine_id)
        if entry.status != EngineState.COMPLETED:
            raise LifecycleError(
                f"Can only reset engine '{engine_id}' from Completed, "
                f"not from {entry.status.value}.",
                engine_id=engine_id,
                current_state=entry.status.value,
                attempted_state=EngineState.READY.value,
                stage="reset",
            )
        entry.status = EngineState.READY
        entry.error = None
        self._log.info(
            "Engine reset to Ready",
            {"engine_id": engine_id, "stage": "reset"},
        )

    # -----------------------------------------------------------------
    # Dependency validation
    # -----------------------------------------------------------------

    def _validate_dependencies(self, engine_id: str) -> None:
        """Ensure all dependencies of *engine_id* are registered.

        Raises:
            DependencyError: If a dependency is not registered.
        """
        entry = self.get_or_raise(engine_id)
        missing = [
            dep for dep in entry.dependencies
            if dep not in self._entries
        ]
        if missing:
            self._log.error(
                "Engine has unregistered dependencies",
                {
                    "engine_id": engine_id,
                    "missing_dependencies": missing,
                    "stage": "dependency_validation",
                },
            )
            raise DependencyError(
                f"Engine '{engine_id}' depends on unregistered engines: "
                + ", ".join(sorted(missing)),
                engine_id=engine_id,
                missing=missing,
                stage="dependency_validation",
            )

    def _check_dependencies_completed(self, engine_id: str) -> bool:
        """Return ``True`` when all dependencies of *engine_id* completed."""
        entry = self.get_or_raise(engine_id)
        for dep in entry.dependencies:
            dep_entry = self._entries.get(dep)
            if dep_entry is None or dep_entry.status != EngineState.COMPLETED:
                return False
        return True

    def _unmet_dependencies(self, engine_id: str) -> List[str]:
        """Return the list of dependencies not yet completed."""
        entry = self.get_or_raise(engine_id)
        unmet: List[str] = []
        for dep in entry.dependencies:
            dep_entry = self._entries.get(dep)
            if dep_entry is None:
                unmet.append(f"{dep} (not registered)")
            elif dep_entry.status != EngineState.COMPLETED:
                unmet.append(f"{dep} (state={dep_entry.status.value})")
        return unmet

    # -----------------------------------------------------------------
    # Security enforcement
    # -----------------------------------------------------------------

    def _enforce_runnable(self, engine_id: str) -> None:
        """Enforce security rules before running *engine_id*.

        Raises:
            SecurityError: If any security rule is violated.
        """
        entry = self._entries.get(engine_id)
        if entry is None:
            raise SecurityError(
                f"Engine '{engine_id}' is not registered. "
                "Unregistered engines cannot run.",
                engine_id=engine_id, rule="no_unregistered",
                stage="security",
            )
        if not entry.enabled:
            raise SecurityError(
                f"Engine '{engine_id}' is disabled and cannot run.",
                engine_id=engine_id, rule="disabled",
                stage="security",
            )
        if entry.status != EngineState.READY:
            raise SecurityError(
                f"Engine '{engine_id}' is in state {entry.status.value}, "
                "not Ready. Only Ready engines can run.",
                engine_id=engine_id, rule="not_ready",
                stage="security",
            )

    # -----------------------------------------------------------------
    # Failure handling
    # -----------------------------------------------------------------

    def _fail(self, engine_id: str, reason: str,
              stage: str = "execute") -> None:
        """Mark *engine_id* as failed and record the failure.

        This is the single point through which all engine failures flow.
        It sets the engine state to ``Failed``, records the error
        reason, logs the failure with full context, and marks the whole
        manager as failed so the pipeline stops.
        """
        entry = self._entries.get(engine_id)
        if entry is None:
            self._log.error(
                "Failure reported for unknown engine",
                {"engine_id": engine_id, "reason": reason, "stage": stage},
            )
            return
        # Transition to FAILED (allowed from any active state).
        entry.status = EngineState.FAILED
        entry.error = reason
        self._failed = True
        self._failed_engine_id = engine_id
        self._failure_stage = stage
        self._log.error(
            "Engine FAILED — pipeline will stop",
            {
                "engine_id": engine_id,
                "name": entry.name,
                "reason": reason,
                "stage": stage,
            },
        )

    # -----------------------------------------------------------------
    # Single-engine execution
    # -----------------------------------------------------------------

    def run_engine(self, engine_id: str,
                   context: GenerationContext) -> StageResult:
        """Run a single engine, enforcing all security and lifecycle rules.

        This is the *only* way an engine is executed.  It enforces:

        * the engine is registered (security rule: no unregistered),
        * the engine is enabled,
        * the engine is in the ``Ready`` state (security rule: not Ready),
        * all dependencies have completed (dependency validation),
        * the lifecycle transition ``Ready → Running → Completed``.

        On success, the engine's :class:`StageResult` is returned and
        the engine moves to ``Completed``.

        On failure, the engine moves to ``Failed``, the manager marks
        itself as failed, and a :class:`ManagerError` is raised.  The
        pipeline must stop.

        Parameters:
            engine_id: The ID of the engine to run.
            context: The :class:`GenerationContext` to pass to the
                engine's ``execute()`` method.

        Returns:
            The :class:`StageResult` produced by the engine.

        Raises:
            SecurityError: If a security rule is violated.
            DependencyError: If dependencies are not met.
            ManagerError: If the engine fails during execution.
        """
        # 1. Security: registered + enabled + Ready.
        self._enforce_runnable(engine_id)

        # 2. Dependency validation: all dependencies registered.
        self._validate_dependencies(engine_id)

        # 3. Dependency check: all dependencies completed.
        if not self._check_dependencies_completed(engine_id):
            unmet = self._unmet_dependencies(engine_id)
            self._log.error(
                "Engine cannot run — dependencies not completed",
                {
                    "engine_id": engine_id,
                    "unmet_dependencies": unmet,
                    "stage": "dependency_check",
                },
            )
            raise DependencyError(
                f"Engine '{engine_id}' cannot run: dependencies not "
                f"completed: {', '.join(unmet)}",
                engine_id=engine_id,
                missing=unmet,
                stage="dependency_check",
            )

        entry = self.get_or_raise(engine_id)

        # 4. Lifecycle: Ready → Running.
        self._transition(engine_id, EngineState.RUNNING, stage_label="start")
        entry.last_run_started_at = time.time()

        self._log.info(
            "Engine starting",
            {
                "engine_id": engine_id,
                "name": entry.name,
                "stage": "start",
            },
        )

        # 5. Execute the engine.
        result: StageResult
        try:
            result = entry.instance.execute(context)
        except Exception as exc:
            duration = time.time() - entry.last_run_started_at
            entry.last_run_finished_at = time.time()
            entry.last_duration_s = duration
            self._fail(engine_id, str(exc), stage="execute")
            self._log.error(
                "Engine raised exception during execution",
                {
                    "engine_id": engine_id,
                    "name": entry.name,
                    "error": str(exc),
                    "duration_s": round(duration, 4),
                    "stage": "execute",
                },
            )
            raise ManagerError(
                f"Engine '{engine_id}' raised an exception: {exc}",
                engine_id=engine_id, stage="execute",
            ) from exc

        duration = time.time() - entry.last_run_started_at
        entry.last_run_finished_at = time.time()
        entry.last_duration_s = duration

        # 6. Inspect the result.
        if not result.success:
            reason = "; ".join(result.errors) if result.errors else "unknown"
            self._log.error(
                "Engine returned failure result",
                {
                    "engine_id": engine_id,
                    "name": entry.name,
                    "errors": result.errors,
                    "duration_s": round(duration, 4),
                    "stage": "execute",
                },
            )
            self._fail(engine_id, reason, stage="execute")
            return result

        # 7. Lifecycle: Running → Completed.
        self._transition(engine_id, EngineState.COMPLETED,
                         stage_label="complete")
        self._log.info(
            "Engine completed",
            {
                "engine_id": engine_id,
                "name": entry.name,
                "duration_s": round(duration, 4),
                "stage": "complete",
            },
        )
        return result

    # -----------------------------------------------------------------
    # Full managed run
    # -----------------------------------------------------------------

    def run_all(self, context: GenerationContext) -> ManagerResult:
        """Run every enabled engine in dependency-aware order.

        The manager:

        1. Loads and initializes every enabled engine (lifecycle up to
           ``Ready``).
        2. Builds the execution queue.
        3. Runs engines one by one, in queue order.
        4. Stops the moment any engine fails — no continuation.
        5. Logs the duration of each engine and the total run.

        Returns a :class:`ManagerResult` summarising the whole run.
        """
        start = time.time()
        self._failed = False
        self._failed_engine_id = None
        self._failure_stage = None

        self._log.info(
            "Managed run starting",
            {"engine_count": self.count(), "stage": "run_all"},
        )

        results: List[StageResult] = []
        errors: List[str] = []

        try:
            # Phase 1: bring every enabled engine to Ready.
            self._bring_all_to_ready()

            # Phase 2: build the queue.
            queue_items = self._queue.rebuild(self._entries)
            self._log.info(
                "Execution queue built",
                {
                    "order": [q.engine_id for q in queue_items],
                    "stage": "queue",
                },
            )

            # Phase 3: run engines in queue order.
            completed_ids: Set[str] = set()
            for item in queue_items:
                entry = self._entries[item.engine_id]

                # Skip disabled engines (shouldn't be in the queue, but
                # double-check for safety).
                if not entry.enabled:
                    continue

                # The engine should be in Ready state by now.
                if entry.status != EngineState.READY:
                    # If dependencies completed but engine isn't ready
                    # (e.g. it was disabled mid-run), skip it.
                    if entry.is_terminal:
                        completed_ids.add(item.engine_id)
                        continue
                    self._log.warning(
                        "Engine not in Ready state, skipping",
                        {
                            "engine_id": item.engine_id,
                            "state": entry.status.value,
                            "stage": "run_all",
                        },
                    )
                    continue

                # Run the engine.
                result = self.run_engine(item.engine_id, context)
                results.append(result)

                if not result.success:
                    errors.extend(result.errors)
                    # The manager is now failed — stop the pipeline.
                    self._log.error(
                        "Managed run stopping due to engine failure",
                        {
                            "engine_id": item.engine_id,
                            "name": entry.name,
                            "stage": "stop",
                        },
                    )
                    break

                completed_ids.add(item.engine_id)

        except ManagerError as exc:
            errors.append(str(exc))
            self._log.error(
                "Managed run aborted by manager error",
                {
                    "engine_id": exc.engine_id,
                    "stage": exc.stage,
                    "error": str(exc),
                },
            )
        except Exception as exc:  # pragma: no cover - safety net
            errors.append(f"Unexpected manager error: {exc}")
            self._log.error(
                "Managed run aborted by unexpected error",
                {"error": str(exc), "stage": "run_all"},
            )

        total = time.time() - start
        success = not self._failed and not errors

        result = ManagerResult(
            success=success,
            engine_results=results,
            errors=errors,
            failed_engine_id=self._failed_engine_id,
            failure_stage=self._failure_stage,
            total_duration_s=round(total, 4),
            metadata={
                "engines_run": len(results),
                "engines_total": self.count(),
            },
        )

        if success:
            self._log.info(
                "Managed run completed successfully",
                {
                    "engines_run": len(results),
                    "total_duration_s": round(total, 4),
                    "stage": "run_all",
                },
            )
        else:
            self._log.error(
                "Managed run completed with failures",
                {
                    "failed_engine_id": self._failed_engine_id,
                    "failure_stage": self._failure_stage,
                    "total_duration_s": round(total, 4),
                    "stage": "stop",
                },
            )

        return result

    # -----------------------------------------------------------------
    # Lifecycle helper: bring all enabled engines to Ready
    # -----------------------------------------------------------------

    def _bring_all_to_ready(self) -> None:
        """Load, initialize, and mark ready every enabled engine.

        Processes engines in registration order so the logs are
        predictable.  Skips engines that are already past a given
        stage (idempotent).
        """
        for engine_id, entry in self._entries.items():
            if not entry.enabled:
                self._log.info(
                    "Engine is disabled, skipping lifecycle",
                    {"engine_id": engine_id, "stage": "lifecycle"},
                )
                continue

            # Load.
            if entry.status == EngineState.REGISTERED:
                self.load(engine_id)

            # Initialize.
            if entry.status == EngineState.LOADED:
                self.initialize(engine_id)

            # Mark ready.
            if entry.status == EngineState.INITIALIZED:
                self.mark_ready(engine_id)

    # -----------------------------------------------------------------
    # Introspection (read-only views for the pipeline / caller)
    # -----------------------------------------------------------------

    def queue_order(self) -> List[QueueItem]:
        """Return the current execution queue order (read-only)."""
        return self._queue.rebuild(self._entries)

    def states(self) -> Dict[str, str]:
        """Return a mapping of engine_id → current state name."""
        return {eid: e.status.value for eid, e in self._entries.items()}

    def is_failed(self) -> bool:
        """Return ``True`` if the manager has recorded a failure."""
        return self._failed

    def failed_engine(self) -> Optional[str]:
        """Return the ID of the failed engine, if any."""
        return self._failed_engine_id

    def failure_stage(self) -> Optional[str]:
        """Return the lifecycle stage at which the failure occurred."""
        return self._failure_stage

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"CoreEngineManager(engines={self.count()}, "
            f"failed={self._failed})"
        )


__all__ = [
    "CoreEngineManager",
    "ManagerResult",
]
