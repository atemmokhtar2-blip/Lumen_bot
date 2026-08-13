"""
Error types specific to the Core Engine Manager (Specification 003).

These errors extend the existing :class:`~core.errors.EngineError`
hierarchy so that callers can catch ``EngineError`` for any failure,
while the manager can raise precise sub-types for:

* lifecycle violations (illegal state transitions, skipping stages),
* dependency failures (missing or unmet dependencies),
* security violations (unregistered engines, self-starting, bypassing),
* duplicate engine IDs,
* unknown engine references.

No exception in this module is ever raised *during normal operation* —
they surface contract violations that must stop the pipeline.
"""

from __future__ import annotations

from typing import List, Optional

from ..core.errors import EngineError


# ---------------------------------------------------------------------------
# Base manager error
# ---------------------------------------------------------------------------

class ManagerError(EngineError):
    """Base exception for every error produced by the Core Engine Manager.

    All manager-specific errors derive from this class so that callers
    can distinguish "a manager policy was violated" from ordinary
    engine execution errors.
    """

    def __init__(self, message: str, *, engine_id: Optional[str] = None,
                 stage: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.engine_id = engine_id
        self.stage = stage
        self.details = details or {}

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        base = super().__str__()
        parts = [base]
        if self.engine_id:
            parts.append(f"engine_id={self.engine_id}")
        if self.stage:
            parts.append(f"stage={self.stage}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Lifecycle violations
# ---------------------------------------------------------------------------

class LifecycleError(ManagerError):
    """Raised when an engine lifecycle rule is violated.

    This includes:

    * attempting an illegal state transition,
    * skipping a required lifecycle stage,
    * requesting an operation that the current state does not allow.
    """

    def __init__(self, message: str, *, engine_id: Optional[str] = None,
                 current_state: Optional[str] = None,
                 attempted_state: Optional[str] = None,
                 stage: Optional[str] = None,
                 details: Optional[dict] = None):
        super().__init__(message, engine_id=engine_id, stage=stage,
                         details=details)
        self.current_state = current_state
        self.attempted_state = attempted_state


# ---------------------------------------------------------------------------
# Dependency failures
# ---------------------------------------------------------------------------

class DependencyError(ManagerError):
    """Raised when an engine's dependencies are not satisfied.

    The manager refuses to run an engine when:

    * a declared dependency is not registered,
    * a declared dependency has not completed successfully,
    * a circular dependency is detected.

    The ``missing`` list names the dependencies that were not met.
    """

    def __init__(self, message: str, *, engine_id: Optional[str] = None,
                 missing: Optional[List[str]] = None,
                 stage: Optional[str] = None,
                 details: Optional[dict] = None):
        super().__init__(message, engine_id=engine_id, stage=stage,
                         details=details)
        self.missing = missing or []


# ---------------------------------------------------------------------------
# Security violations
# ---------------------------------------------------------------------------

class SecurityError(ManagerError):
    """Raised when a security rule of the manager is violated.

    Security rules (all enforced by the manager, never by engines):

    * an unregistered engine attempted to run,
    * an engine not in the ``Ready`` state attempted to run,
    * an engine attempted to start itself directly,
    * an engine attempted to bypass the manager.

    The ``rule`` attribute identifies which rule was violated.
    """

    def __init__(self, message: str, *, engine_id: Optional[str] = None,
                 rule: Optional[str] = None,
                 stage: Optional[str] = None,
                 details: Optional[dict] = None):
        super().__init__(message, engine_id=engine_id, stage=stage,
                         details=details)
        self.rule = rule


# ---------------------------------------------------------------------------
# Registration errors
# ---------------------------------------------------------------------------

class DuplicateEngineError(ManagerError):
    """Raised when an engine ID is registered more than once.

    The manager enforces unique IDs; re-registering the same ID is a
    hard error, not a silent overwrite.
    """

    def __init__(self, engine_id: str, *,
                 details: Optional[dict] = None):
        super().__init__(
            f"Engine ID '{engine_id}' is already registered. "
            "Duplicate IDs are not allowed.",
            engine_id=engine_id, stage="register",
            details=details,
        )
        self.engine_id = engine_id


class UnknownEngineError(ManagerError):
    """Raised when a referenced engine ID is not known to the manager."""

    def __init__(self, engine_id: str, *,
                 details: Optional[dict] = None):
        super().__init__(
            f"Engine ID '{engine_id}' is not registered with the manager.",
            engine_id=engine_id, details=details,
        )
        self.engine_id = engine_id


__all__ = [
    "ManagerError",
    "LifecycleError",
    "DependencyError",
    "SecurityError",
    "DuplicateEngineError",
    "UnknownEngineError",
]
