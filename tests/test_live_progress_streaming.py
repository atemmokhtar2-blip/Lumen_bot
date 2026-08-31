"""Progress: engine events update status text."""
from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location("m", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_bus_cross_thread():
    bus = _load("lumen/engine/services/progress_bus.py")
    got = []
    tok = bus.set_progress_handler(lambda e: got.append(e))
    try:
        def w():
            t = bus.set_progress_handler(lambda e: got.append(e))
            try:
                bus.report_progress({"tool": "write_file", "path": "a.py"})
            finally:
                bus.reset_progress_handler(t)
        import threading
        threading.Thread(target=w).start()
        time.sleep(0.2)
    finally:
        bus.reset_progress_handler(tok)
    assert any(x.get("tool") == "write_file" for x in got)


def test_agent_emits():
    src = (ROOT / "lumen/engine/services/cline_runtime/agent_loop.py").read_text()
    assert "tool_start" in src and "tool_done" in src


def test_heartbeat_edits_on_events():
    pt = _load("lumen/bot/progress_tracker.py")

    class Msg:
        def __init__(self):
            self.texts = []
            self.message_id = 1
            self.chat_id = 1

        async def edit_text(self, text, **k):
            self.texts.append(text)

    def gen():
        from lumen.engine.services.progress_bus import report_progress
        report_progress({"tool": "write_file", "path": "bot.py", "step": 1, "limit": 5})
        time.sleep(0.1)
        report_progress({"tool": "finish", "ok": True, "step": 2})
        return "ok"

    async def run():
        m = Msg()
        assert await pt.run_with_heartbeat(gen, status_msg=m, user_id=1) == "ok"
        await asyncio.sleep(0.3)
        assert m.texts
        assert not pt.is_generation_busy(1)

    asyncio.run(run())
