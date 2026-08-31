"""Live generation progress — real agent events on the Telegram status message.

Architecture
------------
Engine code (agent_loop, coding_agent) emits via ``lumen.engine.services.progress_bus``
(no bot imports). ``run_with_heartbeat`` installs a handler that feeds a thread-safe
sink; an asyncio task edits the Telegram status message with tool/file/step details.

The handler is re-bound **inside** the worker thread so events are never lost when
``asyncio.to_thread`` does not preserve contextvars the way we need.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Callable, Optional

from lumen.engine.services.progress_bus import (
    report_progress as bus_report,
    reset_progress_handler,
    set_progress_handler,
)

_BUSY: dict[int, float] = {}
_BUSY_LOCK = threading.Lock()

_TOOL_AR = {
    "list_dir": "استعراض المجلدات",
    "tree": "مسح شجرة المشروع",
    "read_file": "قراءة ملف",
    "read_files": "قراءة ملفات",
    "write_file": "كتابة ملف",
    "edit_file": "تعديل ملف",
    "search_replace": "بحث واستبدال",
    "apply_edits": "تطبيق تعديلات",
    "apply_patch": "تطبيق باتش",
    "grep_codebase": "بحث في الكود",
    "glob_files": "البحث عن ملفات",
    "run_shell": "تنفيذ أمر",
    "find_symbol": "بحث عن رمز",
    "get_symbol_source": "قراءة مصدر الرمز",
    "find_references": "مراجع الرمز",
    "blast_radius": "تحليل التأثير",
    "code_search": "بحث دلالي",
    "browser_navigate": "تصفح صفحة",
    "browser_content": "قراءة صفحة",
    "browser_click": "نقر في المتصفح",
    "browser_fill": "تعبئة حقل",
    "browser_screenshot": "لقطة شاشة",
    "run_skill": "تشغيل مهارة",
    "finish": "إنهاء وبناء النتيجة",
    "generate_bot": "توليد بوت",
    "refine_bot": "تعديل بوت",
    "coding_agent": "وكيل البرمجة",
}


def report_progress(event: dict[str, Any] | None) -> None:
    """Public alias — prefer engine progress_bus from agent code."""
    bus_report(event)


def mark_generation_busy(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid <= 0:
        return
    with _BUSY_LOCK:
        _BUSY[uid] = time.monotonic()


def clear_generation_busy(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid <= 0:
        return
    with _BUSY_LOCK:
        _BUSY.pop(uid, None)


def is_generation_busy(user_id: int, *, stale_after: float = 600.0) -> bool:
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    with _BUSY_LOCK:
        started = _BUSY.get(uid)
        if started is None:
            return False
        if time.monotonic() - started > float(stale_after):
            _BUSY.pop(uid, None)
            return False
        return True


def _format_event(event: dict[str, Any], *, elapsed: int, step: int, limit: int) -> str:
    phase = str(event.get("phase") or "step")
    tool = str(event.get("tool") or phase or "").strip()
    thought = str(event.get("thought") or "").strip().replace("\n", " ")[:120]
    path = str(event.get("path") or event.get("file") or "").strip()
    ok = event.get("ok")
    detail = str(event.get("detail") or "").strip()[:100]
    tool_ar = _TOOL_AR.get(tool, tool)

    lines = [
        "⚙️ جاري البناء عبر الوكيل…",
        f"⏱ {elapsed}ث  ·  خطوة {step}" + (f"/{limit}" if limit else ""),
    ]
    if tool:
        status = ""
        if ok is True:
            status = " ✅"
        elif ok is False:
            status = " ⚠️"
        lines.append(f"🔧 {tool_ar}{status}")
    if path:
        short = path if len(path) <= 48 else "…" + path[-46:]
        lines.append(f"📄 `{short}`")
    if thought:
        lines.append(f"💭 {thought}")
    if detail and detail != thought:
        lines.append(f"ℹ️ {detail}")
    files_n = event.get("files_written")
    if isinstance(files_n, int) and files_n > 0:
        lines.append(f"📁 ملفات مكتوبة: {files_n}")
    return "\n".join(lines)[:3500]


class ProgressSink:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._seq = 0
        self._step = 0
        self._limit = 0

    def push(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            ev = dict(event)
            if "step" in ev:
                try:
                    self._step = int(ev["step"])
                except Exception:
                    pass
            if "limit" in ev:
                try:
                    self._limit = int(ev["limit"])
                except Exception:
                    pass
            ev["_seq"] = self._seq
            self._latest = ev

    def snapshot(self) -> tuple[int, dict[str, Any] | None, int, int]:
        with self._lock:
            return (
                self._seq,
                dict(self._latest) if self._latest else None,
                self._step,
                self._limit,
            )


class ProgressHeartbeat:
    POLL = 1.0
    KEEP_ALIVE = 10.0

    def __init__(self, status_msg, *, interval: float | None = None) -> None:
        self.status_msg = status_msg
        self.interval = float(interval or self.POLL)
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._started = time.monotonic()
        self.sink = ProgressSink()
        self._last_seq = 0
        self._last_edit = 0.0

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                break
            except asyncio.TimeoutError:
                await self._tick()

    async def _tick(self) -> None:
        seq, event, step, limit = self.sink.snapshot()
        elapsed = int(time.monotonic() - self._started)
        now = time.monotonic()
        if seq == self._last_seq and (now - self._last_edit) < self.KEEP_ALIVE:
            return
        if event:
            text = _format_event(event, elapsed=elapsed, step=step or seq, limit=limit)
        else:
            text = (
                "⚙️ جاري تجهيز الوكيل وبدء البناء…\n"
                f"⏱ مرّ {elapsed} ثانية\n"
                "كل أداة ينفّذها الوكيل هتظهر هنا مباشرة."
            )
        try:
            await self.status_msg.edit_text(text)
            self._last_seq = seq
            self._last_edit = now
        except Exception:
            pass

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        # Flush latest agent events before teardown (short jobs finish before first poll)
        try:
            await self._tick()
        except Exception:
            pass
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                self._task.cancel()


def _heartbeat_timeout() -> float:
    try:
        inner = float(os.getenv("GENERATION_TIMEOUT_SEC") or "180")
    except ValueError:
        inner = 180.0
    return max(30.0, min(600.0, inner) + 30.0)


async def run_with_heartbeat(
    fn: Callable[..., Any],
    *args,
    status_msg,
    user_id: int = 0,
    **kwargs,
) -> Any:
    """Run blocking generation while streaming progress_bus events to Telegram."""
    hb = ProgressHeartbeat(status_msg)
    sink = hb.sink

    def _on_event(event: dict[str, Any]) -> None:
        sink.push(event)

    def _thread_main() -> Any:
        # Re-bind inside the worker thread — critical for reliable delivery
        token = set_progress_handler(_on_event)
        try:
            bus_report({"phase": "starting", "detail": "بدء حلقة التوليد", "step": 0})
            return fn(*args, **kwargs)
        finally:
            reset_progress_handler(token)

    uid = int(user_id or 0)
    if uid:
        mark_generation_busy(uid)
    # Also bind on the event-loop thread so any sync pre-work can report
    token_main = set_progress_handler(_on_event)
    sink.push({"phase": "starting", "detail": "بدء حلقة الوكيل"})
    hb.start()
    try:
        timeout = _heartbeat_timeout()
        return await asyncio.wait_for(
            asyncio.to_thread(_thread_main),
            timeout=timeout,
        )
    finally:
        reset_progress_handler(token_main)
        await hb.stop()
        if uid:
            clear_generation_busy(uid)


__all__ = [
    "ProgressHeartbeat",
    "run_with_heartbeat",
    "report_progress",
    "mark_generation_busy",
    "clear_generation_busy",
    "is_generation_busy",
]
