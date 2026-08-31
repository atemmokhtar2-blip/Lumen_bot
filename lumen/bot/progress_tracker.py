"""Live generation progress — real agent events, not fake rotating phases.

Root model (Dead Wait fix)
--------------------------
``run_agent`` emits structured events via ``report_progress`` (contextvar).
A background asyncio task drains those events and edits the Telegram status
message so the user sees the actual tool / file / step — not a static spinner.

Also exposes a per-user busy flag so concurrent messages/buttons during
generation get a clear response instead of a second parallel generation.
"""
from __future__ import annotations

import asyncio
import contextvars
import os
import threading
import time
from typing import Any, Callable, Optional

# Thread-safe sink set by run_with_heartbeat (works across asyncio.to_thread)
_progress_sink: contextvars.ContextVar[Optional["ProgressSink"]] = contextvars.ContextVar(
    "lumen_progress_sink", default=None
)

# user_id -> generation started monotonic time (busy guard)
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
}


def report_progress(event: dict[str, Any] | None) -> None:
    """Called from the agent thread after each meaningful step."""
    if not event:
        return
    sink = _progress_sink.get()
    if sink is not None:
        sink.push(event)


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
    tool = str(event.get("tool") or "").strip()
    thought = str(event.get("thought") or "").strip().replace("\n", " ")[:120]
    path = str(event.get("path") or event.get("file") or "").strip()
    ok = event.get("ok")
    detail = str(event.get("detail") or "").strip()[:100]
    tool_ar = _TOOL_AR.get(tool, tool or phase)

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
    """Thread-safe event buffer drained by the asyncio UI loop."""

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
            return self._seq, (dict(self._latest) if self._latest else None), self._step, self._limit


class ProgressHeartbeat:
    """Edit status message whenever a new agent event arrives (or keep-alive)."""

    POLL = 1.2
    KEEP_ALIVE = 12.0

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
                "سيتم عرض كل أداة ينفّذها الوكيل هنا."
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
    """Run blocking generation in a thread while streaming agent events to Telegram."""
    hb = ProgressHeartbeat(status_msg)
    token = _progress_sink.set(hb.sink)
    uid = int(user_id or 0)
    if uid:
        mark_generation_busy(uid)
    hb.sink.push({"phase": "starting", "detail": "بدء حلقة الوكيل"})
    hb.start()
    try:
        timeout = _heartbeat_timeout()
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=timeout,
        )
    finally:
        _progress_sink.reset(token)
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
