"""Phase 3 tests — Weakness 2: Dead Wait (streaming progress feed).

Verifies:
1. AgentProgressFeed is thread-safe and records the latest action.
2. format_agent_action produces correct Arabic labels for all known tools.
3. The ContextVar propagates from set_progress_callback into asyncio.to_thread
   so run_agent (deep in the call chain) receives the callback WITHOUT threading
   on_step through every intermediate signature.
4. _emit_step falls back to the ContextVar when the explicit on_step is None.
5. ProgressHeartbeat.INTERVAL is 3.0 (not the old 20.0).
"""
import asyncio
import contextvars
import threading
import time

import pytest


# --------------------------------------------------------------------------- #
# 1. AgentProgressFeed — thread safety + latest()
# --------------------------------------------------------------------------- #
def test_feed_push_and_latest():
    from lumen.bot.progress_tracker import AgentProgressFeed

    feed = AgentProgressFeed()
    assert feed.latest() == ("", 0, 0)

    feed.push(1, "read_file", {"path": "main.py"}, True)
    text, step, total = feed.latest()
    assert step == 1
    assert total == 1
    assert "قراءة ملف" in text
    assert "main.py" in text
    assert "✓" in text  # ok=True

    feed.push(2, "write_file", {"path": "bot.py"}, False)
    text, step, total = feed.latest()
    assert step == 2
    assert total == 2
    assert "كتابة ملف" in text
    assert "↻" in text  # ok=False (retry indicator)


def test_feed_thread_safety():
    """Concurrent pushes from multiple threads must not corrupt state."""
    from lumen.bot.progress_tracker import AgentProgressFeed

    feed = AgentProgressFeed()

    def worker(start_idx: int):
        for i in range(100):
            feed.push(start_idx + i, "read_file", {"path": f"f{i}.py"}, True)

    threads = [threading.Thread(target=worker, args=(s,)) for s in (0, 100, 200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    _, _, total = feed.latest()
    assert total == 300  # all pushes recorded, none lost


# --------------------------------------------------------------------------- #
# 2. format_agent_action — Arabic labels
# --------------------------------------------------------------------------- #
def test_format_agent_action_all_tools():
    from lumen.bot.progress_tracker import format_agent_action, _TOOL_LABELS_AR
    from lumen.engine.services.cline_runtime.agent_loop import AGENT_TOOL_NAMES

    # Every official tool must have an Arabic label
    for name in AGENT_TOOL_NAMES:
        assert name in _TOOL_LABELS_AR, f"Missing Arabic label for tool: {name}"

    # Spot-check a few
    assert "قراءة ملف" in format_agent_action(1, "read_file", {"path": "x.py"}, True)
    assert "كتابة ملف" in format_agent_action(1, "write_file", {"path": "y.py"}, True)
    assert "تصفّح الإنترنت" in format_agent_action(1, "browser_navigate", {"url": "https://x.com"}, True)
    assert "إنهاء التوليد" in format_agent_action(1, "finish", {"summary": "done"}, True)


def test_format_agent_action_unknown_tool_falls_back():
    from lumen.bot.progress_tracker import format_agent_action

    # Unknown tool name falls back to the raw name
    text = format_agent_action(1, "unknown_tool", None, True)
    assert "unknown_tool" in text


def test_format_agent_action_no_tool():
    from lumen.bot.progress_tracker import format_agent_action

    text = format_agent_action(1, None, None, False)
    assert "الخطوة" in text  # "thinking..." fallback


# --------------------------------------------------------------------------- #
# 3. ContextVar propagation through asyncio.to_thread
# --------------------------------------------------------------------------- #
def test_contextvar_propagates_to_thread():
    """The ContextVar set in the event loop must be visible in the thread."""
    from lumen.engine.services.cline_runtime.agent_loop import (
        set_progress_callback,
        reset_progress_callback,
        _CURRENT_ON_STEP,
    )

    received = []

    def cb(idx, tool, args, ok):
        received.append((idx, tool, args, ok))

    async def run():
        token = set_progress_callback(cb)
        try:
            def thread_fn():
                # Simulate what run_agent does deep in the chain
                cb_from_cv = _CURRENT_ON_STEP.get()
                assert cb_from_cv is not None, "ContextVar not visible in thread"
                cb_from_cv(42, "read_file", {"path": "x.py"}, True)
                return "done"

            result = await asyncio.to_thread(thread_fn)
            return result
        finally:
            reset_progress_callback(token)

    result = asyncio.run(run())
    assert result == "done"
    assert len(received) == 1
    assert received[0] == (42, "read_file", {"path": "x.py"}, True)


# --------------------------------------------------------------------------- #
# 4. _emit_step falls back to ContextVar when on_step=None
# --------------------------------------------------------------------------- #
def test_emit_step_falls_back_to_contextvar():
    from lumen.engine.services.cline_runtime.agent_loop import (
        _emit_step,
        set_progress_callback,
        reset_progress_callback,
    )

    received = []

    def cb(idx, tool, args, ok):
        received.append((idx, tool, args, ok))

    token = set_progress_callback(cb)
    try:
        # Call _emit_step with on_step=None — should use the ContextVar
        _emit_step(None, 5, "write_file", {"path": "main.py"}, True)
        assert len(received) == 1
        assert received[0] == (5, "write_file", {"path": "main.py"}, True)
    finally:
        reset_progress_callback(token)


def test_emit_step_no_callback_no_error():
    """When neither on_step nor ContextVar is set, _emit_step is a no-op."""
    from lumen.engine.services.cline_runtime.agent_loop import _emit_step, _CURRENT_ON_STEP

    # Ensure no callback is set
    assert _CURRENT_ON_STEP.get() is None
    # Should not raise
    _emit_step(None, 1, "read_file", {"path": "x.py"}, True)


def test_emit_step_explicit_on_step_takes_priority():
    from lumen.engine.services.cline_runtime.agent_loop import (
        _emit_step,
        set_progress_callback,
        reset_progress_callback,
    )

    cv_received = []
    explicit_received = []

    token = set_progress_callback(lambda i, t, a, ok: cv_received.append((i, t, a, ok)))
    try:
        def explicit_cb(idx, tool, args, ok):
            explicit_received.append((idx, tool, args, ok))

        # Explicit on_step should take priority over the ContextVar
        _emit_step(explicit_cb, 3, "finish", {"summary": "done"}, True)
        assert len(explicit_received) == 1
        assert len(cv_received) == 0  # ContextVar callback NOT called
    finally:
        reset_progress_callback(token)


# --------------------------------------------------------------------------- #
# 5. ProgressHeartbeat.INTERVAL is 3.0
# --------------------------------------------------------------------------- #
def test_heartbeat_interval_is_3_seconds():
    from lumen.bot.progress_tracker import ProgressHeartbeat

    assert ProgressHeartbeat.INTERVAL == 3.0, (
        f"Expected INTERVAL=3.0 (streaming), got {ProgressHeartbeat.INTERVAL}"
    )


# --------------------------------------------------------------------------- #
# 6. End-to-end: run_with_heartbeat + feed → real action streamed
# --------------------------------------------------------------------------- #
def test_run_with_heartbeat_streams_real_actions():
    """Simulates the full flow: feed → contextvar → deep function → heartbeat sees action."""
    from lumen.bot.progress_tracker import (
        AgentProgressFeed,
        run_with_heartbeat,
        format_agent_action,
    )
    from lumen.engine.services.cline_runtime.agent_loop import _CURRENT_ON_STEP

    feed = AgentProgressFeed()

    class FakeStatusMsg:
        def __init__(self):
            self.edits = []

        async def edit_text(self, text, **kw):
            self.edits.append(text)

    status_msg = FakeStatusMsg()

    def deep_function():
        """Simulates run_agent deep in the call chain — reads the ContextVar."""
        cb = _CURRENT_ON_STEP.get()
        assert cb is not None, "ContextVar should be set by run_with_heartbeat"
        # Simulate 3 agent actions
        cb(0, "read_file", {"path": "main.py"}, True)
        cb(1, "write_file", {"path": "bot.py"}, True)
        cb(2, "finish", {"summary": "done"}, True)
        return "success"

    async def run():
        return await run_with_heartbeat(
            deep_function,
            status_msg=status_msg,
            feed=feed,
        )

    result = asyncio.run(run())
    assert result == "success"

    # The feed should have recorded all 3 actions
    _, _, total = feed.latest()
    assert total == 3, f"Expected 3 actions in feed, got {total}"

    # The latest action should be "finish"
    text, step, _ = feed.latest()
    assert step == 2
    assert "إنهاء التوليد" in text


def test_contextvar_reset_after_run_with_heartbeat():
    """After run_with_heartbeat completes, the ContextVar should be reset."""
    from lumen.bot.progress_tracker import AgentProgressFeed, run_with_heartbeat
    from lumen.engine.services.cline_runtime.agent_loop import _CURRENT_ON_STEP

    feed = AgentProgressFeed()

    class FakeStatusMsg:
        async def edit_text(self, text, **kw):
            pass

    def dummy():
        return "ok"

    async def run():
        return await run_with_heartbeat(dummy, status_msg=FakeStatusMsg(), feed=feed)

    asyncio.run(run())
    # After completion, the ContextVar should be back to None
    assert _CURRENT_ON_STEP.get() is None, "ContextVar should be reset after run_with_heartbeat"
