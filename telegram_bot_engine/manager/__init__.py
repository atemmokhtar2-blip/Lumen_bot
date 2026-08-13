"""
Core Engine Manager package (Specification 003).

The Core Engine Manager is the executive brain of the Telegram Bot
Generation Engine.  It does **not** generate code, create files, or
analyse requests.  Its sole purpose is to manage every other engine:

* register engines in a central registry with a unique ID, name,
  version, status, priority, dependencies, and enabled flag,
* enforce a strict lifecycle with no stage skipping,
* validate dependencies before running any engine,
* maintain an internal execution queue determining run order,
* stop the entire pipeline the moment any engine fails,
* log every operation (loading, starting, completing, failing,
  stopping, execution duration),
* enforce security rules (no unregistered engines, no non-Ready
  engines, no self-starting, no bypassing),
* provide clear interfaces so no engine talks to another engine
  directly — all communication flows through the manager.

The manager is designed to scale to hundreds of engines without
redesign; new engines can be added without modifying existing ones.
"""

from .errors import (
    ManagerError,
    LifecycleError,
    DependencyError,
    SecurityError,
    DuplicateEngineError,
    UnknownEngineError,
)
from .lifecycle import EngineState, EngineStateTransition, LIFECYCLE_ORDER
from .engine_entry import EngineEntry, EngineMetadata
from .execution_queue import ExecutionQueue, QueueItem
from .engine_manager import CoreEngineManager, ManagerResult

__all__ = [
    # errors
    "ManagerError",
    "LifecycleError",
    "DependencyError",
    "SecurityError",
    "DuplicateEngineError",
    "UnknownEngineError",
    # lifecycle
    "EngineState",
    "EngineStateTransition",
    "LIFECYCLE_ORDER",
    # data models
    "EngineEntry",
    "EngineMetadata",
    # queue
    "ExecutionQueue",
    "QueueItem",
    # manager
    "CoreEngineManager",
    "ManagerResult",
]
