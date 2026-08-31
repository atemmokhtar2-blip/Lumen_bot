"""Dead Wait — engine progress events reach the user status message."""
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


def test_format_shows_engine_activity_and_trail():
    pt = _load("pt", "lumen/bot/progress_tracker.py")
    hist = [
        {"tool": "thinking", "step": 1},
        {"tool": "write_file", "path": "main.py", "ok": True, "step": 1},
        {"tool": "finish", "ok": True, "step": 2},
    ]
    text = pt._format_event(
        {"tool": "finish", "ok": True, "thought": "done", "files_written": 4},
        elapsed=22,
        step=2,
        limit=12,
        history=hist,
    )
    assert "المحرك شغال" in text
    assert "تفكير" in text or "thinking" in text.lower() or "•" in text
    assert "إنهاء" in text or "finish" in text.lower()
    assert "ملفات مكتوبة" in text
    assert "إلغاء" in text


def test_progress_bus_cross_thread_delivery():
    bus = _load("bus", "lumen/engine/services/progress_bus.py")
    received: list[dict] = []

    def handler(ev):
        received.append(ev)

    token = bus.set_progress_handler(handler)
    try:
        def worker():
            tok = bus.set_progress_handler(handler)
            try:
                bus.report_progress({"tool": "thinking", "step": 1})
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

    assert len(received) >= 3
    assert received[-1]["tool"] == "finish"


def test_agent_loop_emits_thinking_and_tools():
    src = (
        Path(__file__).resolve().parents[1]
        / "lumen/engine/services/cline_runtime/agent_loop.py"
    ).read_text()
    assert "lumen.engine.services.progress_bus" in src
    assert "lumen.bot.progress_tracker" not in src
    assert '"phase": "thinking"' in src
    assert '"phase": "tool_start"' in src
    assert '"phase": "tool_done"' in src


def test_run_with_heartbeat_shows_real_tools():
    pt = _load("pt2", "lumen/bot/progress_tracker.py")

    class FakeMsg:
        def __init__(self):
            self.texts = []

        async def edit_text(self, text):
            self.texts.append(text)

    def fake_generation():
        from lumen.engine.services.progress_bus import report_progress
        report_progress({"phase": "thinking", "tool": "thinking", "step": 1, "limit": 5})
        time.sleep(0.05)
        report_progress({
            "phase": "tool_done", "tool": "write_file", "path": "bot.py",
            "ok": True, "step": 1, "limit": 5, "thought": "create entry",
            "files_written": 1,
        })
        time.sleep(0.05)
        report_progress({"phase": "tool_done", "tool": "finish", "ok": True, "step": 2, "limit": 5})
        return {"ok": True}

    async def run():
        msg = FakeMsg()
        result = await pt.run_with_heartbeat(fake_generation, status_msg=msg, user_id=99)
        assert result == {"ok": True}
        await asyncio.sleep(0.2)
        joined = "\n".join(msg.texts)
        assert "المحرك شغال" in joined or "وكيل" in joined or "كتابة" in joined or "إنهاء" in joined, joined
        assert not pt.is_generation_busy(99)
        return joined

    assert asyncio.run(run())


def test_busy_guard_lifecycle():
    pt = _load("pt3", "lumen/bot/progress_tracker.py")
    assert not pt.is_generation_busy(7)
    pt.mark_generation_busy(7)
    assert pt.is_generation_busy(7)
    pt.clear_generation_busy(7)
    assert not pt.is_generation_busy(7)
