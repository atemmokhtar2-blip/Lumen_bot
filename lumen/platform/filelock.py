"""Cross-process exclusive file locks (fcntl) for JSON/SQLite state files."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows — best-effort no-op lock
    fcntl = None  # type: ignore


@contextmanager
def exclusive_lock(path: str | Path, *, timeout: float = 10.0) -> Iterator[None]:
    """Exclusive lock tied to path.lock — works across processes."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")
    deadline = time.monotonic() + timeout
    try:
        if fcntl is None:
            yield
            return
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"lock_timeout:{lock_path}")
                time.sleep(0.02)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass


def atomic_write_text(path: str | Path, text: str) -> None:
    """Write via temp file + replace to avoid partial JSON on crash."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
