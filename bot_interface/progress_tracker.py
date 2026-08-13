"""Heartbeat updates during long-running generation so users know the bot is alive."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional


class ProgressHeartbeat:
    INTERVAL = 20.0

    def __init__(self, status_msg, *, interval: float | None = None) -> None:
        self.status_msg = status_msg
        self.interval = float(interval or self.INTERVAL)
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._started = time.monotonic()
        self._step = 0

    async def _loop(self) -> None:
        phases = [
            "⏳ جاري التحليل وبناء المواصفات...",
            "⏳ جاري توليد الأوامر والمعالجات...",
            "⏳ جاري التحقق ضد الهلوسة...",
            "⏳ ما زال التوليد يعمل — لحظات...",
        ]
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                break
            except asyncio.TimeoutError:
                self._step += 1
                elapsed = int(time.monotonic() - self._started)
                text = phases[min(self._step, len(phases) - 1)]
                text = f"{text}\n⏱ مرّ {elapsed} ثانية"
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


async def run_with_heartbeat(
    fn: Callable[..., Any],
    *args,
    status_msg,
    **kwargs,
) -> Any:
    hb = ProgressHeartbeat(status_msg)
    hb.start()
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    finally:
        await hb.stop()


__all__ = ["ProgressHeartbeat", "run_with_heartbeat"]
