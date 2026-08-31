"""Dead Wait fix — real agent progress events, not static phases."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_progress():
    path = Path(__file__).resolve().parents[1] / "lumen" / "bot" / "progress_tracker.py"
    spec = importlib.util.spec_from_file_location("lumen_progress_tracker_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_format_shows_real_tool_not_fake_phase():
    pt = _load_progress()
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
    assert "ملفات مكتوبة: 3" in text
    # Must NOT be the old static phase-only copy alone
    assert "جاري التحليل وبناء المواصفات" not in text


def test_report_progress_reaches_sink():
    pt = _load_progress()
    sink = pt.ProgressSink()
    tok = pt._progress_sink.set(sink)
    try:
        pt.report_progress({"tool": "read_file", "path": "main.py", "step": 1, "limit": 10})
        pt.report_progress({"tool": "write_file", "path": "bot.py", "step": 2, "limit": 10, "ok": True})
    finally:
        pt._progress_sink.reset(tok)
    seq, ev, step, limit = sink.snapshot()
    assert seq == 2
    assert ev["tool"] == "write_file"
    assert step == 2
    assert limit == 10


def test_busy_guard_lifecycle():
    pt = _load_progress()
    assert not pt.is_generation_busy(7)
    pt.mark_generation_busy(7)
    assert pt.is_generation_busy(7)
    pt.clear_generation_busy(7)
    assert not pt.is_generation_busy(7)


def test_agent_loop_emits_progress_hooks():
    src = (Path(__file__).resolve().parents[1] / "lumen/engine/services/cline_runtime/agent_loop.py").read_text()
    assert "def _emit_progress" in src
    assert '"phase": "tool_start"' in src or "'phase': 'tool_start'" in src
    assert '"phase": "tool_done"' in src or "'phase': 'tool_done'" in src
    assert "report_progress" in src
