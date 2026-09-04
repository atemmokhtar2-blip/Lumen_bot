"""Live status while the engine runs — one sink, one edit loop."""
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

_AR = {
    "thinking": "تفكير",
    "read_file": "قراءة",
    "read_files": "قراءة",
    "write_file": "كتابة",
    "edit_file": "تعديل",
    "run_shell": "أمر",
    "grep_codebase": "بحث",
    "glob_files": "ملفات",
    "apply_edits": "تعديلات",
    "apply_patch": "باتش",
    "finish": "إنهاء",
    "coding_agent": "وكيل برمجة",
    "orchestrate": "تنسيق",
    "starting": "بدء",
    "loop_start": "حلقة",
    "plan_start": "تخطيط",
    "work_start": "تنفيذ",
    "critique_start": "مراجعة",
    "repair_start": "إصلاح",
    "deliver_start": "تسليم",
    "temporal": "مسار بعيد",
}


def report_progress(event: dict[str, Any] | None) -> None:
    bus_report(event)


def mark_generation_busy(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid > 0:
        with _BUSY_LOCK:
            _BUSY[uid] = time.monotonic()


def clear_generation_busy(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid > 0:
        with _BUSY_LOCK:
            _BUSY.pop(uid, None)


def is_generation_busy(user_id: int, *, stale_after: float = 600.0) -> bool:
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    with _BUSY_LOCK:
        t0 = _BUSY.get(uid)
        if t0 is None:
            return False
        if time.monotonic() - t0 > stale_after:
            _BUSY.pop(uid, None)
            return False
        return True


def _text(ev: dict[str, Any] | None, elapsed: int, log: list[str]) -> str:
    tool = str((ev or {}).get("tool") or (ev or {}).get("phase") or "")
    path = str((ev or {}).get("path") or (ev or {}).get("file") or "")[:50]
    detail = str((ev or {}).get("detail") or "")[:80]
    thought = str((ev or {}).get("thought") or "").replace("\n", " ")[:100]
    step = (ev or {}).get("step")
    limit = (ev or {}).get("limit")
    name = _AR.get(tool, tool or "…")

    lines = [f"⚙️ {name} · {elapsed}ث"]
    if step is not None:
        lines[0] += f" · {step}" + (f"/{limit}" if limit else "")
    if path:
        lines.append(f"📄 {path}")
    if detail:
        lines.append(f"ℹ️ {detail}")
    if thought:
        lines.append(f"💭 {thought}")
    provider = str((ev or {}).get("provider") or "")[:20]
    model = str((ev or {}).get("model") or (ev or {}).get("underlying_model") or "")[:40]
    if provider or model:
        lines.append(f"🧠 {provider}" + (f"/{model}" if model else ""))
    if log:
        lines.append("—")
        lines.extend(f"• {x}" for x in log[-5:])
    lines.append("إلغاء: /cancel")
    return "\n".join(lines)[:3500]


class ProgressHeartbeat:
    def __init__(self, status_msg, *, bot=None, chat_id=None) -> None:
        self.status_msg = status_msg
        self.bot = bot
        self.chat_id = chat_id
        self._lock = threading.Lock()
        self._ev: dict[str, Any] | None = None
        self._log: list[str] = []
        self._seq = 0
        self._started = time.monotonic()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._last_seq = -1

    def push(self, event: dict[str, Any]) -> None:
        if not event:
            return
        with self._lock:
            self._seq += 1
            self._ev = dict(event)
            tool = str(event.get("tool") or event.get("phase") or "")
            path = str(event.get("path") or "")[:40]
            if tool:
                line = f"{_AR.get(tool, tool)}" + (f" {path}" if path else "")
                if not self._log or self._log[-1] != line:
                    self._log.append(line)
                    self._log = self._log[-12:]

    async def _edit(self, text: str) -> None:
        msg = self.status_msg
        if msg is None:
            return
        try:
            bot = self.bot or getattr(msg, "get_bot", lambda: None)()
            chat_id = self.chat_id or getattr(msg, "chat_id", None) or getattr(
                getattr(msg, "chat", None), "id", None
            )
            mid = getattr(msg, "message_id", None)
            if bot and chat_id and mid:
                await bot.edit_message_text(chat_id=int(chat_id), message_id=int(mid), text=text)
                return
        except Exception as e:
            if "not modified" in str(e).lower():
                return
        try:
            await msg.edit_text(text)
        except Exception:
            pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                seq, ev, log = self._seq, self._ev, list(self._log)
            elapsed = int(time.monotonic() - self._started)
            if seq != self._last_seq or elapsed % 3 == 0:
                await self._edit(_text(ev, elapsed, log))
                self._last_seq = seq
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=0.7)
                break
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        with self._lock:
            ev, log = self._ev, list(self._log)
        await self._edit(_text(ev, int(time.monotonic() - self._started), log))
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                self._task.cancel()


async def run_with_heartbeat(
    fn: Callable[..., Any],
    *args,
    status_msg,
    user_id: int = 0,
    context=None,
    **kwargs,
) -> Any:
    bot = getattr(context, "bot", None) if context is not None else None
    chat_id = getattr(status_msg, "chat_id", None) or getattr(
        getattr(status_msg, "chat", None), "id", None
    )
    hb = ProgressHeartbeat(status_msg, bot=bot, chat_id=chat_id)

    def on_event(event: dict[str, Any]) -> None:
        hb.push(event)

    def worker() -> Any:
        tok = set_progress_handler(on_event)
        try:
            bus_report({"phase": "starting", "tool": "starting", "step": 0})
            return fn(*args, **kwargs)
        finally:
            reset_progress_handler(tok)

    uid = int(user_id or 0)
    if uid:
        mark_generation_busy(uid)
    tok = set_progress_handler(on_event)
    hb.push({"tool": "starting", "detail": "بدء المحرك"})
    hb.start()
    try:
        try:
            inner = float(os.getenv("GENERATION_TIMEOUT_SEC") or "180")
        except ValueError:
            inner = 180.0
        timeout = max(30.0, min(600.0, inner) + 30.0)
        return await asyncio.wait_for(asyncio.to_thread(worker), timeout=timeout)
    finally:
        reset_progress_handler(tok)
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
