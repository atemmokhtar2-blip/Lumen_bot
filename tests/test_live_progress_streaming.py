"""Dead Wait — prove engine progress reaches the UI sink across threads."""
from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path


def _load(name: str, rel: str):
    path = Path(__file__).resolve().parents[1] / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_format_shows_real_tool_not_fake_phase():
    pt = _load("pt", "lumen/bot/progress_tracker.py")
    text = pt._format_event(
        {
            "phase": "tool_done",
            "tool": "write_file",
            "path": "handlers/start.py",
            "ok": True,
            "thought": "add start command handler",
            "files_written": 3,
        },
        elapsed=12,
        step=4,
        limit=12,
    )
    assert "كتابة ملف" in text
    assert "handlers/start.py" in text
    assert "خطوة 4/12" in text
    assert "جاري التحليل وبناء المواصفات" not in text


def test_progress_bus_cross_thread_delivery():
    """Root proof: worker thread emit → main sink receives (to_thread simulation)."""
    bus = _load("bus", "lumen/engine/services/progress_bus.py")
    received: list[dict] = []

    def handler(ev):
        received.append(ev)

    token = bus.set_progress_handler(handler)
    try:
        def worker():
            # Re-bind inside worker like run_with_heartbeat does
            tok = bus.set_progress_handler(handler)
            try:
                bus.report_progress({"tool": "write_file", "path": "main.py", "step": 1})
                bus.report_progress({"tool": "finish", "ok": True, "step": 2})
            finally:
                bus.reset_progress_handler(tok)

        import threading
        th = threading.Thread(target=worker)
        th.start()
        th.join(timeout=5)
    finally:
        bus.reset_progress_handler(token)

    assert len(received) >= 2
    assert received[-1]["tool"] == "finish"
    assert received[0]["path"] == "main.py"


def test_agent_loop_emit_uses_progress_bus_not_bot_import():
    src = (Path(__file__).resolve().parents[1] / "lumen/engine/services/cline_runtime/agent_loop.py").read_text()
    assert "lumen.engine.services.progress_bus" in src
    assert "lumen.bot.progress_tracker" not in src
    assert "tool_start" in src and "tool_done" in src


def test_run_with_heartbeat_delivers_worker_events():
    """Full UI path: run_with_heartbeat + synthetic worker that emits like agent_loop."""
    pt = _load("pt2", "lumen/bot/progress_tracker.py")
    bus = _load("bus2", "lumen/engine/services/progress_bus.py")

    class FakeMsg:
        def __init__(self):
            self.texts = []

        async def edit_text(self, text):
            self.texts.append(text)

    def fake_generation():
        # Same import path agent_loop uses
        from lumen.engine.services.progress_bus import report_progress
        report_progress({"phase": "tool_start", "tool": "write_file", "path": "bot.py", "step": 1, "limit": 5})
        time.sleep(0.05)
        report_progress({
            "phase": "tool_done", "tool": "write_file", "path": "bot.py",
            "ok": True, "step": 1, "limit": 5, "thought": "create bot entry",
        })
        time.sleep(0.05)
        report_progress({"phase": "tool_done", "tool": "finish", "ok": True, "step": 2, "limit": 5})
        return {"ok": True}

    async def run():
        msg = FakeMsg()
        result = await pt.run_with_heartbeat(fake_generation, status_msg=msg, user_id=99)
        assert result == {"ok": True}
        # Allow final ticks
        await asyncio.sleep(0.3)
        joined = "\n".join(msg.texts)
        assert any(x in joined for x in ("كتابة ملف", "write_file", "bot.py", "إنهاء", "finish", "الوكيل")), joined
        assert not pt.is_generation_busy(99)
        return joined

    text = asyncio.run(run())
    assert text


def test_busy_guard_lifecycle():
    pt = _load("pt3", "lumen/bot/progress_tracker.py")
    assert not pt.is_generation_busy(7)
    pt.mark_generation_busy(7)
    assert pt.is_generation_busy(7)
    pt.clear_generation_busy(7)
    assert not pt.is_generation_busy(7)
