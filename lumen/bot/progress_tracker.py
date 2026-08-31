"""Live progress updates during long-running generation.

Replaces the old "dead wait" (20s interval + 4 static generic messages, user
saw only "typing..." for ~20s) with a real streaming feed: the agent loop
pushes its actual actions ("read file main.py", "wrote bot.py", "searched
codebase") into a thread-safe ``AgentProgressFeed`` and the heartbeat edits
the status message every ~3 seconds with the LATEST real action + elapsed
time, so the user always sees what the agent is doing.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Callable, Optional


# --------------------------------------------------------------------------- #
# Thread-safe progress feed (written from the agent thread, read from the
# asyncio heartbeat in the event loop).
# --------------------------------------------------------------------------- #
class AgentProgressFeed:
    """Latest agent action, shared across the agent thread and the UI loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: str = ""
        self._step: int = 0
        self._total_tools: int = 0

    def push(self, step_index: int, tool_name: str | None, args: dict | None, ok: bool) -> None:
        """Record the latest agent action (called from the agent thread)."""
        text = format_agent_action(step_index, tool_name, args, ok)
        with self._lock:
            self._latest = text
            self._step = step_index
            self._total_tools += 1

    def latest(self) -> tuple[str, int, int]:
        """Return (latest_action_text, step_index, total_tools) (called from UI loop)."""
        with self._lock:
            return self._latest, self._step, self._total_tools

    def on_step(self, step_index: int, tool_name: str | None, args: dict | None, ok: bool) -> None:
        """Callback signature for run_agent(on_step=...)."""
        self.push(step_index, tool_name, args, ok)


# Arabic, user-facing descriptions of each agent tool action.
_TOOL_LABELS_AR: dict[str, str] = {
    "list_dir": "تصفّح المجلدات",
    "tree": "عرض شجرة المشروع",
    "read_file": "قراءة ملف",
    "read_files": "قراءة ملفات",
    "write_file": "كتابة ملف",
    "edit_file": "تعديل ملف",
    "search_replace": "بحث واستبدال",
    "apply_edits": "تطبيق تعديلات",
    "apply_patch": "تطبيق رقعة",
    "grep_codebase": "بحث في الكود",
    "glob_files": "البحث عن ملفات",
    "run_shell": "تنفيذ أمر",
    "find_symbol": "تحليل رمز برمجي",
    "get_symbol_source": "قراءة مصدر رمز",
    "find_references": "البحث عن مراجع",
    "blast_radius": "تحليل أثر التغيير",
    "code_search": "بحث في الكود",
    "browser_navigate": "تصفّح الإنترنت",
    "browser_content": "قراءة محتوى صفحة",
    "browser_click": "النقر على عنصر",
    "browser_fill": "ملء حقل",
    "browser_screenshot": "التقاط لقطة شاشة",
    "run_skill": "تشغيل مهارة",
    "finish": "إنهاء التوليد",
}


def format_agent_action(step_index: int, tool_name: str | None, args: dict | None, ok: bool) -> str:
    """Build a concise Arabic line describing one agent step."""
    if not tool_name:
        return f"الخطوة {step_index}: يفكّر..."
    label = _TOOL_LABELS_AR.get(tool_name, tool_name)
    # Include the target path/query when available, trimmed for readability.
    detail = ""
    if args:
        for key in ("path", "file", "target", "query", "pattern", "url", "command", "cmd"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                detail = " " + val.strip().splitlines()[0][:60]
                break
    status = "✓" if ok else "↻"
    return f"{label}{detail} {status}"


# --------------------------------------------------------------------------- #
# Heartbeat — edits the status message every ~3s with the latest real action.
# --------------------------------------------------------------------------- #
class ProgressHeartbeat:
    INTERVAL = 3.0  # was 20.0 — Weakness 2 fix: stream real actions every ~3s

    def __init__(self, status_msg, *, interval: float | None = None, feed: AgentProgressFeed | None = None) -> None:
        self.status_msg = status_msg
        self.interval = float(interval or self.INTERVAL)
        self.feed = feed
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._started = time.monotonic()
        self._step = 0

    async def _loop(self) -> None:
        # Generic fallback phases shown only when the agent has not yet pushed
        # a real action (e.g. during the initial LLM call before the first tool).
        phases = [
            "⏳ جاري التحليل وبناء المواصفات...",
            "⏳ جاري التخطيط للخطوات...",
            "⏳ جاري الانتظار لردّ النموذج...",
        ]
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                break
            except asyncio.TimeoutError:
                self._step += 1
                elapsed = int(time.monotonic() - self._started)
                # Prefer the REAL agent action when available.
                action_text = ""
                tool_count = 0
                if self.feed is not None:
                    action_text, _step_idx, tool_count = self.feed.latest()
                if action_text:
                    body = f"🛠️ {action_text}"
                    if tool_count:
                        body += f"\n🔧 الأداة #{tool_count}"
                else:
                    body = phases[min(self._step - 1, len(phases) - 1)] if self._step >= 1 else phases[0]
                text = f"{body}\n⏱ مرّ {elapsed} ثانية"
                try:
                    await self.status_msg.edit_text(text)
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
    """Outer wall-clock guarantee for run_with_heartbeat.

    Slightly above GENERATION_TIMEOUT_SEC so the inner engine timeout fires
    first (producing a precise error), but this outer bound catches any path
    that bypasses the inner timeout (defense-in-depth).
    """
    try:
        inner = float(os.getenv("GENERATION_TIMEOUT_SEC") or "180")
    except ValueError:
        inner = 180.0
    # Cap at 600s (same as GENERATION_TIMEOUT_SEC max), add 30s grace
    return max(30.0, min(600.0, inner) + 30.0)


async def run_with_heartbeat(
    fn: Callable[..., Any],
    *args,
    status_msg,
    feed: AgentProgressFeed | None = None,
    **kwargs,
) -> Any:
    """Run ``fn`` in a thread with a live progress heartbeat.

    If ``feed`` is provided, the feed's ``on_step`` callback is installed into
    the current context via a ContextVar before the threaded call. Because
    ``asyncio.to_thread`` copies the context, the callback propagates into the
    worker thread and is visible to ``run_agent`` deep inside the call chain
    (run_generation → execute_ir → execute_cline_ir → run_agent) WITHOUT
    needing to thread ``on_step`` through every intermediate signature.
    """
    hb = ProgressHeartbeat(status_msg, feed=feed)
    hb.start()
    _token = None
    try:
        timeout = _heartbeat_timeout()
        call_kwargs = dict(kwargs)
        if feed is not None:
            # Wire the feed as on_step if the top-level fn accepts it directly.
            if _accepts_on_step(fn):
                call_kwargs.setdefault("on_step", feed.on_step)
            # ALWAYS set the ContextVar so run_agent (deep in the chain) can
            # read it as a fallback even if intermediate callers don't pass it.
            from lumen.engine.services.cline_runtime.agent_loop import set_progress_callback
            _token = set_progress_callback(feed.on_step)
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **call_kwargs),
            timeout=timeout,
        )
    finally:
        if _token is not None:
            try:
                from lumen.engine.services.cline_runtime.agent_loop import reset_progress_callback
                reset_progress_callback(_token)
            except Exception:
                pass
        await hb.stop()


def _accepts_on_step(fn: Callable[..., Any]) -> bool:
    """True if ``fn`` declares an ``on_step`` parameter (so we can wire the feed)."""
    try:
        import inspect

        sig = inspect.signature(fn)
        params = sig.parameters
        return "on_step" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except Exception:
        return False


__all__ = ["AgentProgressFeed", "ProgressHeartbeat", "run_with_heartbeat", "format_agent_action"]
