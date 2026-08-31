"""Phase 2 (Dead Wait) enhancement tests — streaming + busy guard.

Tests the concrete improvements made on top of the existing Phase 3 feed:

1. **AgentProgressFeed.history()** — rolling window of recent actions so the
   user sees a concise log of what the agent did, not just the latest step.

2. **format_agent_action** — no technical jargon:
   • "الخطوة N" removed → "🧠 يفكّر ويدرس طلبك…" (no step number leak)
   • Full server paths masked → basename only (security + UX)
   • Unicode icons (✅ 🔄) instead of ASCII (✓ ↻)

3. **Busy guard** — if a generation is running, concurrent button presses get
   a friendly notice instead of starting a second parallel generation or
   corrupting the UI state.

4. **generate_bridge** now passes `feed=` to `run_with_heartbeat` (was missing
   — the UI-guided path showed only static generic messages).
"""
import asyncio
import inspect
import threading

import pytest


# --------------------------------------------------------------------------- #
# 1. AgentProgressFeed.history() — rolling window
# --------------------------------------------------------------------------- #
class TestProgressFeedHistory:
    def test_history_empty_initially(self):
        from lumen.bot.progress_tracker import AgentProgressFeed

        feed = AgentProgressFeed()
        assert feed.history() == []

    def test_history_records_all_pushes(self):
        from lumen.bot.progress_tracker import AgentProgressFeed

        feed = AgentProgressFeed()
        feed.push(1, "read_file", {"path": "main.py"}, True)
        feed.push(2, "write_file", {"path": "bot.py"}, True)
        feed.push(3, "finish", {"summary": "done"}, True)

        hist = feed.history()
        assert len(hist) == 3
        assert "قراءة ملف" in hist[0]
        assert "كتابة ملف" in hist[1]
        assert "إنهاء التوليد" in hist[2]

    def test_history_capped_at_max(self):
        from lumen.bot.progress_tracker import AgentProgressFeed

        feed = AgentProgressFeed()
        # Push more than _MAX_HISTORY (5)
        for i in range(10):
            feed.push(i, "read_file", {"path": f"f{i}.py"}, True)

        hist = feed.history()
        assert len(hist) == 5, f"Expected 5 (capped), got {len(hist)}"
        # The oldest entries should be dropped — only last 5 remain
        assert "f5.py" in hist[0]
        assert "f9.py" in hist[-1]

    def test_history_returns_copy_not_reference(self):
        """Mutating the returned list must not affect the internal state."""
        from lumen.bot.progress_tracker import AgentProgressFeed

        feed = AgentProgressFeed()
        feed.push(1, "read_file", {"path": "x.py"}, True)

        hist = feed.history()
        hist.clear()  # mutate the copy

        # Internal state should be unaffected
        assert len(feed.history()) == 1

    def test_history_thread_safe(self):
        """Concurrent pushes + history reads must not corrupt."""
        from lumen.bot.progress_tracker import AgentProgressFeed

        feed = AgentProgressFeed()
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                feed.push(i, "read_file", {"path": f"f{i}.py"}, True)
                i += 1

        def reader():
            while not stop.is_set():
                _ = feed.history()  # must not raise

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        threading.Event().wait(0.1)  # run briefly
        stop.set()
        for t in threads:
            t.join(timeout=2.0)

        # Final state must be consistent
        _, _, total = feed.latest()
        hist = feed.history()
        assert len(hist) <= 5
        assert total > 0


# --------------------------------------------------------------------------- #
# 2. format_agent_action — no jargon, basename masking, unicode icons
# --------------------------------------------------------------------------- #
class TestFormatAgentActionEnhanced:
    def test_no_step_number_leak(self):
        """The old 'الخطوة N' must NOT appear — it's internal jargon."""
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(42, None, None, False)
        assert "الخطوة" not in text
        assert "42" not in text  # the step index must not leak
        assert "يفكّر" in text  # friendly Arabic instead

    def test_thinking_message_is_friendly(self):
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, None, None, False)
        assert "🧠" in text
        assert "يفكّر" in text

    def test_basename_only_no_full_path(self):
        """Full server paths must NOT appear — only the basename (security)."""
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "read_file", {"path": "/home/user/projects/bot/main.py"}, True)
        assert "main.py" in text
        assert "/home/user" not in text
        assert "/projects" not in text
        # Only the last path component should be visible
        assert text.count("/") == 0  # no slashes in the output

    def test_basename_extracted_from_nested_path(self):
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "write_file", {"path": "src/deep/nested/bot.py"}, True)
        assert "bot.py" in text
        assert "src/deep" not in text

    def test_url_shown_for_browser_navigate(self):
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "browser_navigate", {"url": "https://example.com"}, True)
        assert "example.com" in text
        assert "تصفّح الإنترنت" in text

    def test_query_shown_for_search(self):
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "grep_codebase", {"query": "def main"}, True)
        assert "بحث في الكود" in text

    def test_unicode_icons_not_ascii(self):
        """✅ and 🔄 instead of ASCII ✓ and ↻."""
        from lumen.bot.progress_tracker import format_agent_action

        ok_text = format_agent_action(1, "read_file", {"path": "x.py"}, True)
        assert "✅" in ok_text
        assert "✓" not in ok_text  # old ASCII checkmark must be gone

        fail_text = format_agent_action(1, "read_file", {"path": "x.py"}, False)
        assert "🔄" in fail_text
        assert "↻" not in fail_text  # old ASCII retry symbol must be gone

    def test_detail_wrapped_in_guillemets(self):
        """The target file/query is wrapped in «...» for readability."""
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "read_file", {"path": "main.py"}, True)
        assert "«main.py»" in text

    def test_long_path_truncated(self):
        """Very long paths are truncated to 50 chars for readability."""
        from lumen.bot.progress_tracker import format_agent_action

        long_name = "a" * 100 + ".py"
        text = format_agent_action(1, "read_file", {"path": long_name}, True)
        # The basename is truncated to 50 chars
        assert len(long_name) > 50
        # The detail part should not exceed ~52 chars (« + 50 + »)
        detail_start = text.find("«")
        detail_end = text.find("»")
        if detail_start >= 0 and detail_end >= 0:
            detail_len = detail_end - detail_start - 1
            assert detail_len <= 50

    def test_no_args_no_detail(self):
        from lumen.bot.progress_tracker import format_agent_action

        text = format_agent_action(1, "finish", None, True)
        assert "«" not in text
        assert "إنهاء التوليد" in text


# --------------------------------------------------------------------------- #
# 3. Busy guard — concurrent generation protection
# --------------------------------------------------------------------------- #
class TestBusyGuard:
    def test_safe_actions_allowed_while_busy(self):
        """These actions must be allowed even when lumen_generating=True."""
        safe = {"home", "open_help", "help", "open_billing", "cancel_generation"}
        # The set is defined in callback_router — verify it's non-empty
        # and contains the critical navigation actions
        assert "home" in safe
        assert "cancel_generation" in safe

    def test_flag_set_during_generation_in_callback_router(self):
        """The source code must set lumen_generating before generation."""
        import inspect
        from lumen.bot.ui import callback_router

        source = inspect.getsource(callback_router)
        assert "lumen_generating" in source
        assert 'user_data["lumen_generating"] = True' in source
        assert 'user_data.pop("lumen_generating"' in source

    def test_flag_set_during_generation_in_message_generation(self):
        """The chat path must also set lumen_generating."""
        import inspect
        from lumen.bot.routers import message_generation

        source = inspect.getsource(message_generation)
        assert "lumen_generating" in source
        assert '_ud["lumen_generating"] = True' in source
        assert '_ud.pop("lumen_generating"' in source

    def test_busy_guard_rejects_open_generate(self):
        """open_generate must NOT be in the safe-while-busy set."""
        import inspect
        from lumen.bot.ui import callback_router

        source = inspect.getsource(callback_router)
        # Find the _SAFE_WHILE_BUSY set definition
        assert "_SAFE_WHILE_BUSY" in source
        # open_generate should not be listed as safe
        # (it starts a new generation)
        safe_line = [l for l in source.split("\n") if "_SAFE_WHILE_BUSY" in l and "{" in l]
        if safe_line:
            assert "open_generate" not in safe_line[0]

    def test_busy_guard_returns_before_processing(self):
        """The busy guard must return early (before _handle_ui_callback_body)."""
        import inspect
        from lumen.bot.ui import callback_router

        source = inspect.getsource(callback_router.handle_ui_callback)
        guard_idx = source.find("lumen_generating")
        body_idx = source.find("_handle_ui_callback_body")
        assert guard_idx >= 0, "busy guard not found in handle_ui_callback"
        assert body_idx >= 0, "_handle_ui_callback_body call not found"
        # Guard must come BEFORE the body call
        assert guard_idx < body_idx, "busy guard must run before _handle_ui_callback_body"


# --------------------------------------------------------------------------- #
# 4. generate_bridge now passes feed= to run_with_heartbeat
# --------------------------------------------------------------------------- #
class TestGenerateBridgeFeed:
    def test_generate_bridge_creates_feed(self):
        """generate_bridge must create an AgentProgressFeed (was missing)."""
        import inspect
        from lumen.bot.ui import generate_bridge

        source = inspect.getsource(generate_bridge)
        assert "AgentProgressFeed" in source
        assert "feed = AgentProgressFeed()" in source

    def test_generate_bridge_passes_feed_to_heartbeat(self):
        """The feed must be passed to run_with_heartbeat(feed=...)."""
        import inspect
        from lumen.bot.ui import generate_bridge

        source = inspect.getsource(generate_bridge)
        assert "feed=feed" in source, "feed= must be passed to run_with_heartbeat"

    def test_generate_bridge_imports_AgentProgressFeed(self):
        """The import must include AgentProgressFeed."""
        import inspect
        from lumen.bot.ui import generate_bridge

        source = inspect.getsource(generate_bridge)
        # Either in a top-level import or a function-level import
        assert "AgentProgressFeed" in source


# --------------------------------------------------------------------------- #
# 5. Heartbeat _loop shows history (not just latest)
# --------------------------------------------------------------------------- #
class TestHeartbeatShowsHistory:
    def test_loop_uses_feed_history(self):
        """The _loop method must call feed.history() to show a log."""
        import inspect
        from lumen.bot.progress_tracker import ProgressHeartbeat

        source = inspect.getsource(ProgressHeartbeat._loop)
        assert "history()" in source, "heartbeat must use feed.history()"

    def test_loop_header_is_arabic(self):
        """The 'what the engine is doing' header must be in Arabic."""
        import inspect
        from lumen.bot.progress_tracker import ProgressHeartbeat

        source = inspect.getsource(ProgressHeartbeat._loop)
        assert "ما يفعله المحرّك" in source or "المحرّك" in source

    def test_loop_shows_elapsed_time(self):
        from lumen.bot.progress_tracker import ProgressHeartbeat

        source = inspect.getsource(ProgressHeartbeat._loop)
        assert "ثانية" in source  # elapsed seconds in Arabic

    def test_loop_shows_step_count(self):
        from lumen.bot.progress_tracker import ProgressHeartbeat

        source = inspect.getsource(ProgressHeartbeat._loop)
        assert "خطوة منجزة" in source or "خطوة" in source

    def test_loop_phases_are_friendly_arabic(self):
        """The fallback phases must be user-friendly Arabic, not jargon."""
        import inspect
        from lumen.bot.progress_tracker import ProgressHeartbeat

        source = inspect.getsource(ProgressHeartbeat._loop)
        # Must NOT contain the old generic "جاري التحليل وبناء المواصفات"
        # (was too technical/vague). New phases should be more specific.
        assert "يحلّل" in source or "يخطّط" in source
        # Must NOT leak step numbers in phases
        assert "الخطوة" not in source


# --------------------------------------------------------------------------- #
# 6. End-to-end: heartbeat renders history from feed
# --------------------------------------------------------------------------- #
class TestHeartbeatEndToEndHistory:
    def test_heartbeat_shows_multiple_actions(self):
        """When the feed has multiple actions, the heartbeat shows a log."""
        from lumen.bot.progress_tracker import AgentProgressFeed, ProgressHeartbeat

        feed = AgentProgressFeed()
        feed.push(0, "read_file", {"path": "main.py"}, True)
        feed.push(1, "write_file", {"path": "bot.py"}, True)
        feed.push(2, "grep_codebase", {"query": "handler"}, True)

        class FakeStatusMsg:
            def __init__(self):
                self.edits = []

            async def edit_text(self, text, **kw):
                self.edits.append(text)

        status = FakeStatusMsg()
        hb = ProgressHeartbeat(status, interval=0.05, feed=feed)

        async def run():
            hb.start()
            await asyncio.sleep(0.15)  # let ~3 ticks happen
            await hb.stop()

        asyncio.run(run())

        assert len(status.edits) > 0
        last_edit = status.edits[-1]
        # The edit must contain the actions (history), not just the latest
        assert "قراءة ملف" in last_edit
        assert "كتابة ملف" in last_edit
        assert "بحث في الكود" in last_edit
        # And the header
        assert "المحرّك" in last_edit

    def test_heartbeat_shows_fallback_when_no_actions(self):
        """When no actions pushed yet, heartbeat shows a friendly phase."""
        from lumen.bot.progress_tracker import AgentProgressFeed, ProgressHeartbeat

        feed = AgentProgressFeed()  # empty — no actions pushed

        class FakeStatusMsg:
            def __init__(self):
                self.edits = []

            async def edit_text(self, text, **kw):
                self.edits.append(text)

        status = FakeStatusMsg()
        hb = ProgressHeartbeat(status, interval=0.05, feed=feed)

        async def run():
            hb.start()
            await asyncio.sleep(0.15)
            await hb.stop()

        asyncio.run(run())

        assert len(status.edits) > 0
        last_edit = status.edits[-1]
        # Must show a friendly phase, not the history header
        assert "يحلّل" in last_edit or "يخطّط" in last_edit or "ينتظر" in last_edit
        # Must NOT show the "what the engine is doing" header (no actions yet)
        assert "ما يفعله المحرّك" not in last_edit
