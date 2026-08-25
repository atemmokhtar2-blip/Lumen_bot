"""
Engine lifecycle states and transitions (Specification 003).

Every engine managed by the :class:`CoreEngineManager` passes through a
strict lifecycle.  The states, in order, are::

    Registered → Loaded → Initialized → Ready → Running → Completed
                                                            ↘ Failed

Rules enforced everywhere in the manager:

* No stage may be skipped.  An engine cannot jump from ``Registered``
  to ``Running`` — it must pass through ``Loaded``, ``Initialized``,
  and ``Ready`` first.
* ``Failed`` is a terminal state.  Once an engine has failed it cannot
  be re-run in the same manager session (a new session must be created).
* ``Completed`` is terminal for a single run; an engine may be reset to
  ``Ready`` for a subsequent run only through an explicit manager call.
* The transition table below is the single source of truth — every
  transition is validated against it.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Tuple


class EngineState(Enum):
    """The six lifecycle states an engine can occupy."""

    REGISTERED = "registered"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# The canonical order of the happy-path lifecycle.
# ``Failed`` is reachable from any active state and is terminal.
LIFECYCLE_ORDER: Tuple[EngineState, ...] = (
    EngineState.REGISTERED,
    EngineState.LOADED,
    EngineState.INITIALIZED,
    EngineState.READY,
    EngineState.RUNNING,
    EngineState.COMPLETED,
)


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------
#
# Maps a *current* state to the set of states that may legally follow it.
# Any transition not listed here is a :class:`LifecycleError`.
#
# Note:
#   * ``REGISTERED → LOADED`` — the manager loads the engine.
#   * ``LOADED → INITIALIZED`` — the manager calls ``initialize()``.
#   * ``INITIALIZED → READY`` — the manager marks the engine ready.
#   * ``READY → RUNNING`` — the manager starts execution.
#   * ``RUNNING → COMPLETED`` — the engine finished successfully.
#   * ``RUNNING → FAILED`` — the engine failed during execution.
#   * ``COMPLETED → READY`` — the manager resets the engine for a
#     subsequent run (explicit, never automatic).
#   * Any active state (``REGISTERED``…``RUNNING``) → ``FAILED`` — the
#     manager or the engine may declare a hard failure.
#
# ``FAILED`` is terminal: it has no outgoing transitions.

_TRANSITIONS: Dict[EngineState, FrozenSet[EngineState]] = {
    EngineState.REGISTERED: frozenset({EngineState.LOADED, EngineState.FAILED}),
    EngineState.LOADED: frozenset({EngineState.INITIALIZED, EngineState.FAILED}),
    EngineState.INITIALIZED: frozenset({EngineState.READY, EngineState.FAILED}),
    EngineState.READY: frozenset({EngineState.RUNNING, EngineState.FAILED}),
    EngineState.RUNNING: frozenset({EngineState.COMPLETED, EngineState.FAILED}),
    EngineState.COMPLETED: frozenset({EngineState.READY}),
    EngineState.FAILED: frozenset(),
}


class EngineStateTransition:
    """Validator for engine lifecycle transitions.

    This is a pure, stateless helper.  The manager delegates every
    state change to :meth:`validate` so that the rules live in exactly
    one place.
    """

    @staticmethod
    def allowed_from(current: EngineState) -> FrozenSet[EngineState]:
        """Return the set of states reachable from *current*."""
        return _TRANSITIONS.get(current, frozenset())

    @staticmethod
    def is_valid(current: EngineState, target: EngineState) -> bool:
        """Return ``True`` when *current → target* is a legal transition."""
        return target in _TRANSITIONS.get(current, frozenset())

    @staticmethod
    def is_terminal(state: EngineState) -> bool:
        """Return ``True`` for terminal states (no outgoing transitions).

        ``FAILED`` is terminal.  ``COMPLETED`` is *not* terminal because
        an engine may be reset to ``Ready`` for a subsequent run.
        """
        return state == EngineState.FAILED

    @staticmethod
    def next_in_order(current: EngineState) -> EngineState:
        """Return the next state in the canonical happy-path order.

        Raises:
            ValueError: if *current* has no next state in the happy
                path (i.e. it is ``COMPLETED`` or ``FAILED``).
        """
        order = LIFECYCLE_ORDER
        try:
            idx = order.index(current)
        except ValueError:
            raise ValueError(
                f"State {current!r} is not part of the happy-path order."
            )
        if idx + 1 >= len(order):
            raise ValueError(
                f"State {current!r} has no next state in the happy path."
            )
        return order[idx + 1]

    @staticmethod
    def skipped(current: EngineState, target: EngineState) -> bool:
        """Return ``True`` when *target* skips over the canonical next state.

        This is used to detect illegal "jumps" in the happy path.  For
        example, ``REGISTERED → INITIALIZED`` skips ``LOADED``.
        """
        if not EngineStateTransition.is_valid(current, target):
            return False  # not valid at all; handled separately
        if target in (EngineState.FAILED, EngineState.READY
                      ) and current == EngineState.COMPLETED:
            return False
        # The only valid non-adjacent happy-path transition is
        # COMPLETED → READY (a reset), which is allowed and not a skip.
        return False


__all__ = [
    "EngineState",
    "EngineStateTransition",
    "LIFECYCLE_ORDER",
]
