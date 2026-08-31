"""Live generation progress — real engine events → Telegram status message.

Architecture
------------
- Engine (agent_loop / orchestrator / coding_agent) emits via ``progress_bus``.
- ``run_with_heartbeat`` installs a sink for the generation lifetime.
- ``ProgressHeartbeat`` wakes *immediately* on each event (thread-safe) and
  edits the status message with a professional step log — not a static spinner.
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

_TOOL_AR: dict[str, str] = {
    "thinking": "تفكير",
    "list_dir": "استعراض مجلد",
    "tree": "شجرة المشروع",
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
    "get_symbol_source": "مصدر الرمز",
    "find_references": "مراجع الرمز",
    "blast_radius": "تحليل التأثير",
    "code_search": "بحث دلالي",
    "browser_navigate": "تصفح",
    "browser_content": "قراءة صفحة",
    "browser_click": "نقر",
    "browser_fill": "تعبئة حقل",
    "browser_screenshot": "لقطة شاشة",
    "run_skill": "مهارة",
    "finish": "إنهاء",
    "generate_bot": "توليد بوت",
    "refine_bot": "تعديل بوت",
    "coding_agent": "وكيل البرمجة",
    "orchestrate": "تنسيق الوكلاء",
    "starting": "بدء",
    "loop_start": "بدء الحلقة",
    "decided": "قرار",
    "plan": "تخطيط",
    "plan_start": "تخطيط",
    "plan_done": "انتهى التخطيط",
    "work_start": "تنفيذ",
    "work_alive": "تنفيذ جارٍ",
    "work_done": "انتهى التنفيذ",
    "critique_start": "مراجعة",
    "critique_done": "انتهت المراجعة",
    "repair_start": "إصلاح",
    "repair_done": "انتهى الإصلاح",
    "deliver_start": "تسليم",
    "deliver_done": "تم التسليم",
    "temporal": "مسار بعيد",
    "hitl": "انتظار موافقتك",
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
    t = (tool or "").strip()
    return _TOOL_AR.get(t, t or "…")


def _short_path(path: str, limit: int = 48) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    if len(p) <= limit:
        return p
    return "…" + p[-(limit - 1) :]


def _line_for_event(ev: dict[str, Any]) -> str | None:
    """One human log line for a meaningful engine event."""
    phase = str(ev.get("phase") or "").strip()
    tool = str(ev.get("tool") or phase or "").strip()
    if not tool and not phase:
        return None
    # Skip pure noise duplicates
    if phase == "tool_start" and not ev.get("path") and not ev.get("detail"):
        # still show tool name
        pass
    ok = ev.get("ok")
    if phase == "tool_done" or ok is True:
        mark = "✓"
    elif ok is False:
        mark = "✗"
    elif phase in {"thinking", "decided", "starting", "loop_start"}:
        mark = "·"
    else:
        mark = "→"

    label = _label(tool)
    path = _short_path(str(ev.get("path") or ev.get("file") or ""))
    detail = str(ev.get("detail") or "").strip().replace("\n", " ")
    if len(detail) > 60:
        detail = detail[:59] + "…"

    parts = [f"{mark} {label}"]
    if path:
        parts.append(path)
    if detail and detail != path:
        parts.append(detail)
    return " ".join(parts)


def _format_status(
    *,
    elapsed: int,
    step: int,
    limit: int,
    current: dict[str, Any] | None,
    log: list[str],
) -> str:
    """Professional live status card."""
    lines: list[str] = []
    step_bit = f" · خطوة {step}/{limit}" if limit else (f" · خطوة {step}" if step else "")
    lines.append(f"Lumen · توليد مباشر")
    lines.append(f"⏱ {elapsed}ث{step_bit}")
    lines.append("")

    if current:
        tool = str(current.get("tool") or current.get("phase") or "").strip()
        path = _short_path(str(current.get("path") or current.get("file") or ""), 56)
        thought = str(current.get("thought") or "").strip().replace("\n", " ")[:140]
        detail = str(current.get("detail") or "").strip().replace("\n", " ")[:120]
        ok = current.get("ok")
        status = "تم" if ok is True else ("فشل" if ok is False else "جارٍ")
        lines.append("الآن")
        if tool:
            lines.append(f"  🔧 {_label(tool)} · {status}")
        if path:
            lines.append(f"  📄 {path}")
        if detail and detail not in path:
            lines.append(f"  ℹ️ {detail}")
        if thought:
            lines.append(f"  💭 {thought}")
        files_n = current.get("files_written")
        if isinstance(files_n, int) and files_n > 0:
            lines.append(f"  📁 ملفات: {files_n}")
        ms = current.get("elapsed_ms")
        if isinstance(ms, (int, float)) and ms > 0:
            lines.append(f"  ⌛ {int(ms)}ms")
        lines.append("")

    if log:
        lines.append("السجل")
        for row in log[-8:]:
            lines.append(f"  {row}")
        lines.append("")
    elif not current:
        hints = (
            "تجهيز مسار التوليد…",
            "تحميل السياق والأدوات…",
            "انتظار أول قرار من الوكيل…",
            "المحرك يخطط للخطوة الأولى…",
        )
        lines.append(f"🔄 {hints[min(elapsed // 3, len(hints) - 1)]}")
        lines.append("")

    lines.append("—")
    lines.append("إلغاء: إلغاء أو /cancel")
    return "\n".join(lines)[:3500]


class ProgressSink:
    """Thread-safe event accumulator for one generation."""

    MAX_LOG = 24

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._log: list[str] = []
        self._seq = 0
        self._step = 0
        self._limit = 0
        self._wake: Optional[Callable[[], None]] = None

    def set_wake(self, fn: Callable[[], None] | None) -> None:
        self._wake = fn

    def push(self, event: dict[str, Any]) -> None:
        if not event or not isinstance(event, dict):
            return
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
            line = _line_for_event(ev)
            phase = str(ev.get("phase") or "")
            # Log meaningful milestones (not every thinking duplicate)
            if line and phase in {
                "tool_done", "tool_start", "coding_agent", "orchestrate",
                "plan_start", "plan_done", "work_start", "work_done",
                "critique_start", "critique_done", "repair_start", "repair_done",
                "deliver_start", "loop_start", "finish", "starting",
            }:
                if not self._log or self._log[-1] != line:
                    self._log.append(line)
                    self._log = self._log[-self.MAX_LOG :]
            elif line and phase == "thinking" and (ev.get("thought") or ""):
                if not self._log or self._log[-1] != line:
                    self._log.append(line)
                    self._log = self._log[-self.MAX_LOG :]
        wake = self._wake
        if wake is not None:
            try:
                wake()
            except Exception:
                pass

    def snapshot(self):
        with self._lock:
            return (
                self._seq,
                dict(self._latest) if self._latest else None,
                self._step,
                self._limit,
                list(self._log),
            )


class ProgressHeartbeat:
    """Async loop: wake on engine events, edit Telegram status message."""

    MIN_EDIT_GAP = 0.35  # Telegram-friendly
    KEEP_ALIVE = 2.0     # refresh elapsed even without new events

    def __init__(
        self,
        status_msg,
        *,
        interval: float | None = None,
        bot=None,
        chat_id=None,
    ) -> None:
        self.status_msg = status_msg
        self.interval = float(interval if interval is not None else 0.5)
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._started = time.monotonic()
        self.sink = ProgressSink()
        self._last_seq = -1
        self._last_edit = 0.0
        self._last_text = ""
        self._bot = bot
        self._chat_id = chat_id
        self._aio_loop: Optional[asyncio.AbstractEventLoop] = None

    def _wake_from_thread(self) -> None:
        loop = self._aio_loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._wake.set)
        except Exception:
            pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            await self._tick()

    async def _tick(self) -> None:
        seq, event, step, limit, log = self.sink.snapshot()
        elapsed = int(time.monotonic() - self._started)
        now = time.monotonic()
        new_event = seq != self._last_seq
        if not new_event and (now - self._last_edit) < self.KEEP_ALIVE:
            return
        if new_event and (now - self._last_edit) < self.MIN_EDIT_GAP:
            # coalesce burst — slight delay then render latest
            await asyncio.sleep(self.MIN_EDIT_GAP - (now - self._last_edit))
            seq, event, step, limit, log = self.sink.snapshot()
            elapsed = int(time.monotonic() - self._started)

        text = _format_status(
            elapsed=elapsed,
            step=step or max(seq, 0),
            limit=limit,
            current=event,
            log=log,
        )
        if text == self._last_text and not new_event:
            return
        ok = await self._edit(text)
        if ok:
            self._last_seq = seq
            self._last_edit = time.monotonic()
            self._last_text = text
        # typing indicator
        if self._bot is not None and self._chat_id is not None:
            try:
                await self._bot.send_chat_action(chat_id=self._chat_id, action="typing")
            except Exception:
                pass

    async def _edit(self, text: str) -> bool:
        msg = self.status_msg
        if msg is None:
            return False
        # Prefer bot.edit_message_text (stable across threads / message objects)
        try:
            bot = self._bot or getattr(msg, "get_bot", lambda: None)()
            chat_id = self._chat_id or getattr(msg, "chat_id", None) or getattr(
                getattr(msg, "chat", None), "id", None
            )
            mid = getattr(msg, "message_id", None)
            if bot is not None and chat_id is not None and mid is not None:
                await bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(mid),
                    text=text[:4096],
                )
                return True
        except Exception as exc:
            err = str(exc).lower()
            if "not modified" in err:
                return True
            # fall through
        try:
            from lumen.bot.telegram_text import safe_edit_text
            await safe_edit_text(msg, text, use_markdown=False)
            return True
        except Exception:
            try:
                await msg.edit_text(text[:4096])
                return True
            except Exception as exc2:
                if "not modified" in str(exc2).lower():
                    return True
                return False

    def start(self) -> None:
        try:
            self._aio_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._aio_loop = None
        self.sink.set_wake(self._wake_from_thread)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        try:
            await self._tick()
        except Exception:
            pass
        self._stop.set()
        self._wake.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.5)
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
        if bot is None and status_msg is not None:
            bot = getattr(status_msg, "get_bot", lambda: None)()
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
            bus_report({
                "phase": "starting",
                "tool": "starting",
                "detail": "بدء حلقة التوليد",
                "step": 0,
            })
            return fn(*args, **kwargs)
        finally:
            reset_progress_handler(token)

    uid = int(user_id or 0)
    if uid:
        mark_generation_busy(uid)
    token_main = set_progress_handler(_on_event)
    sink.push({"phase": "starting", "tool": "starting", "detail": "بدء المحرك", "step": 0})
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
