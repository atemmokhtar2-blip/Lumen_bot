"""Live generation progress wired to the real engine event stream.

User-facing status message is driven by ``progress_bus`` events from:
  - agent_loop (thinking → tool_start → tool_done)
  - coding_agent / orchestrator phases
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
    "thinking": "تفكير الوكيل",
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
    "orchestrate": "تنسيق الوكلاء",
    "starting": "بدء التوليد",
    "loop_start": "بدء حلقة الوكيل",
    "decided": "قرار الخطوة",
}


def report_progress(event: dict[str, Any] | None) -> None:
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


def _label(tool: str) -> str:
    return _TOOL_AR.get(tool, tool or "…")


def _format_event(
    event: dict[str, Any],
    *,
    elapsed: int,
    step: int,
    limit: int,
    history: list[dict[str, Any]] | None = None,
) -> str:
    tool = str(event.get("tool") or event.get("phase") or "").strip()
    thought = str(event.get("thought") or "").strip().replace("\n", " ")[:140]
    path = str(event.get("path") or event.get("file") or "").strip()
    ok = event.get("ok")
    detail = str(event.get("detail") or "").strip()[:120]
    files_n = event.get("files_written")

    lines = [
        "⚙️ المحرك شغال — تحديث مباشر",
        f"⏱ {elapsed}ث" + (f"  ·  خطوة {step}/{limit}" if limit else f"  ·  خطوة {step}"),
    ]

    # Trail of recent real actions (so user sees continuous work)
    hist = [h for h in (history or []) if h.get("tool") or h.get("phase")]
    if hist:
        bits = []
        for h in hist[-4:]:
            ht = str(h.get("tool") or h.get("phase") or "")
            mark = "✅" if h.get("ok") is True else ("⚠️" if h.get("ok") is False else "•")
            bits.append(f"{mark} {_label(ht)}")
        if bits:
            lines.append("📋 " + " → ".join(bits))

    if tool:
        status = " ✅" if ok is True else (" ⚠️" if ok is False else "")
        lines.append(f"🔧 الآن: {_label(tool)}{status}")
    if path:
        short = path if len(path) <= 52 else "…" + path[-50:]
        lines.append(f"📄 {short}")
    if thought:
        lines.append(f"💭 {thought}")
    elif detail:
        lines.append(f"ℹ️ {detail}")
    if isinstance(files_n, int) and files_n > 0:
        lines.append(f"📁 ملفات مكتوبة حتى الآن: {files_n}")
    lines.append("—\nللإلغاء: إلغاء أو /cancel")
    return "\n".join(lines)[:3500]


class ProgressSink:
    HISTORY = 6

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._history: list[dict[str, Any]] = []
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
            phase = str(ev.get("phase") or "")
            if ev.get("tool") or phase in {
                "tool_start", "tool_done", "thinking", "decided",
                "coding_agent", "orchestrate", "loop_start",
            }:
                self._history.append(ev)
                self._history = self._history[-self.HISTORY :]

    def snapshot(self):
        with self._lock:
            return (
                self._seq,
                dict(self._latest) if self._latest else None,
                self._step,
                self._limit,
                [dict(x) for x in self._history],
            )


class ProgressHeartbeat:
    POLL = 0.8
    KEEP_ALIVE = 8.0

    def __init__(self, status_msg, *, interval: float | None = None, bot=None, chat_id=None) -> None:
        self.status_msg = status_msg
        self.interval = float(interval or self.POLL)
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._started = time.monotonic()
        self.sink = ProgressSink()
        self._last_seq = 0
        self._last_edit = 0.0
        self._bot = bot
        self._chat_id = chat_id

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                break
            except asyncio.TimeoutError:
                await self._tick()

    async def _tick(self) -> None:
        seq, event, step, limit, history = self.sink.snapshot()
        elapsed = int(time.monotonic() - self._started)
        now = time.monotonic()
        if seq == self._last_seq and (now - self._last_edit) < self.KEEP_ALIVE:
            return
        if event or history:
            text = _format_event(
                event or {},
                elapsed=elapsed,
                step=step or seq,
                limit=limit,
                history=history,
            )
        else:
            text = (
                "⚙️ المحرك شغال — تجهيز الوكيل…\n"
                f"⏱ مرّ {elapsed} ثانية\n"
                "هتشوف كل خطوة حقيقية هنا أول ما تبدأ.\n"
                "—\nللإلغاء: إلغاء أو /cancel"
            )
        try:
            await self.status_msg.edit_text(text)
            self._last_seq = seq
            self._last_edit = now
        except Exception:
            pass
        # Keep chat "typing…" so Telegram shows activity
        if self._bot is not None and self._chat_id is not None:
            try:
                await self._bot.send_chat_action(chat_id=self._chat_id, action="typing")
            except Exception:
                pass

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
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
    context=None,
    **kwargs,
) -> Any:
    bot = None
    chat_id = None
    try:
        bot = getattr(context, "bot", None) if context is not None else None
        chat_id = getattr(status_msg, "chat_id", None) or getattr(
            getattr(status_msg, "chat", None), "id", None
        )
    except Exception:
        pass

    hb = ProgressHeartbeat(status_msg, bot=bot, chat_id=chat_id)
    sink = hb.sink

    def _on_event(event: dict[str, Any]) -> None:
        sink.push(event)

    def _thread_main() -> Any:
        token = set_progress_handler(_on_event)
        try:
            bus_report({"phase": "starting", "tool": "starting", "detail": "بدء حلقة التوليد", "step": 0})
            return fn(*args, **kwargs)
        finally:
            reset_progress_handler(token)

    uid = int(user_id or 0)
    if uid:
        mark_generation_busy(uid)
    token_main = set_progress_handler(_on_event)
    sink.push({"phase": "starting", "tool": "starting", "detail": "بدء المحرك"})
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
