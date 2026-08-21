"""Phase E — circuit breakers per agent/tool (fail-fast under repeated errors)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CircuitState:
    failures: int = 0
    successes: int = 0
    opened_at: float = 0.0
    state: str = "closed"  # closed | open | half_open


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
        name: str = "default",
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_seconds = max(5.0, recovery_seconds)
        self._state = CircuitState()
        self._lock = threading.RLock()

    def allow(self) -> bool:
        with self._lock:
            if self._state.state == "closed":
                return True
            if self._state.state == "open":
                if time.time() - self._state.opened_at >= self.recovery_seconds:
                    self._state.state = "half_open"
                    return True
                return False
            # half_open: allow one trial
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state.successes += 1
            self._state.failures = 0
            self._state.state = "closed"
            self._state.opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._state.failures += 1
            if self._state.failures >= self.failure_threshold or self._state.state == "half_open":
                self._state.state = "open"
                self._state.opened_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.state,
                "failures": self._state.failures,
                "successes": self._state.successes,
                "opened_at": self._state.opened_at,
            }


class CircuitBoard:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name)
            return self._breakers[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: v.snapshot() for k, v in self._breakers.items()}


_BOARD = CircuitBoard()


def get_circuit_board() -> CircuitBoard:
    return _BOARD
