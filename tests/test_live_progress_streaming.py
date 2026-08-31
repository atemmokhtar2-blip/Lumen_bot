"""Live progress: engine events must drive Telegram status (not a static spinner)."""
from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_format_status_shows_current_and_log():
    pt = _load("pt_fmt", "lumen/bot/progress_tracker.py")
    text = pt._format_status(
        elapsed=12,
        step=3,
        limit=20,
        current={
            "tool": "write_file",
            "path": "handlers/shop.py",
            "thought": "أوامر السلة",
            "files_written": 2,
            "ok": None,
        },
        log=["✓ قراءة main.py", "→ كتابة ملف handlers/shop.py"],
    )
    assert "Lumen" in text
    assert "12ث" in text
    assert "handlers/shop.py" in text
    assert "السجل" in text
    assert "أوامر السلة" in text


def test_line_for_event_shell_detail():
    pt = _load("pt_line", "lumen/bot/progress_tracker.py")
    line = pt._line_for_event({
        "phase": "tool_done",
        "tool": "run_shell",
        "detail": "pip install -r requirements.txt",
        "ok": True,
    })
    assert line is not None
    assert "تنفيذ" in line or "أمر" in line
    assert "pip install" in line


def test_cross_thread_bus_delivery():
    bus = _load("bus_ct", "lumen/engine/services/progress_bus.py")
    received: list = []

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
    src = (ROOT / "lumen/engine/services/cline_runtime/agent_loop.py").read_text()
    assert "lumen.engine.services.progress_bus" in src
    assert '"phase": "thinking"' in src
    assert '"phase": "tool_start"' in src
    assert '"phase": "tool_done"' in src
    assert "_detail_hint" in src


def test_run_with_heartbeat_shows_real_tools():
    pt = _load("pt_hb", "lumen/bot/progress_tracker.py")

    class FakeMsg:
        def __init__(self):
            self.texts = []
            self.message_id = 1
            self.chat_id = 1

        async def edit_text(self, text, **kwargs):
            self.texts.append(text)

    def fake_generation():
        from lumen.engine.services.progress_bus import report_progress
        report_progress({"phase": "thinking", "tool": "thinking", "step": 1, "limit": 5, "thought": "أبدأ"})
        time.sleep(0.08)
        report_progress({
            "phase": "tool_done", "tool": "write_file", "path": "bot.py",
            "ok": True, "step": 1, "limit": 5, "thought": "create entry",
            "files_written": 1,
        })
        time.sleep(0.08)
        report_progress({"phase": "tool_done", "tool": "finish", "ok": True, "step": 2, "limit": 5})
        return {"ok": True}

    async def run():
        msg = FakeMsg()
        result = await pt.run_with_heartbeat(fake_generation, status_msg=msg, user_id=99)
        assert result == {"ok": True}
        await asyncio.sleep(0.3)
        joined = "\n".join(msg.texts)
        assert "Lumen" in joined or "توليد" in joined or "كتابة" in joined or "bot.py" in joined, joined
        assert not pt.is_generation_busy(99)
        return joined

    assert asyncio.run(run())


def test_busy_guard_lifecycle():
    pt = _load("pt_busy", "lumen/bot/progress_tracker.py")
    assert not pt.is_generation_busy(7)
    pt.mark_generation_busy(7)
    assert pt.is_generation_busy(7)
    pt.clear_generation_busy(7)
    assert not pt.is_generation_busy(7)


def test_sink_wakes_and_logs_tools():
    pt = _load("pt_sink", "lumen/bot/progress_tracker.py")
    sink = pt.ProgressSink()
    woke = []
    sink.set_wake(lambda: woke.append(1))
    sink.push({"phase": "tool_done", "tool": "write_file", "path": "a.py", "ok": True, "step": 1, "limit": 10})
    sink.push({"phase": "tool_done", "tool": "run_shell", "detail": "pytest", "ok": True, "step": 2, "limit": 10})
    seq, latest, step, limit, log = sink.snapshot()
    assert seq == 2
    assert step == 2
    assert any("a.py" in x for x in log)
    assert woke
