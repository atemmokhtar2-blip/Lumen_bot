"""Generation delivery flow — facade.

Implementation lives in bot_interface.generation_steps (state machine modules).
Public API unchanged for all callers.
"""
from __future__ import annotations

from bot_interface.generation_steps.helpers import _sentry_capture, _smoke_test_project
from bot_interface.generation_steps.delivery import deliver_generation_result

__all__ = ["deliver_generation_result", "_smoke_test_project", "_sentry_capture"]
