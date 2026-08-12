"""Atomic state persistence with exclusive file locks.

Prevents TOCTOU races when multiple concurrent start/stop requests
touch the same hosting instances registry.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

# Process-local lock (threads within one worker)
_THREAD_LOCK = threading.RLock()


@contextmanager
def exclusive_state_lock(lock_path: Path, *, timeout: float = 15.0) -> Iterator[None]:
    """Acquire thread lock + OS advisory lock on ``lock_path``.

    Uses ``fcntl.flock`` when available (POSIX). On platforms without flock,
    falls back to the thread lock only (still serializes in-process).
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure the lock file exists
    if not lock_path.exists():
        try:
            lock_path.touch()
        except OSError:
            pass

    with _THREAD_LOCK:
        fh = None
        try:
            try:
                import fcntl  # POSIX
                fh = open(lock_path, "a+", encoding="utf-8")
                deadline = time.monotonic() + max(0.5, timeout)
                while True:
                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"state lock timeout: {lock_path}")
                        time.sleep(0.05)
            except ImportError:
                fh = None  # Windows / no fcntl — thread lock only
            yield
        finally:
            if fh is not None:
                try:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    fh.close()
                except Exception:
                    pass


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` via temp file + os.replace (atomic on POSIX)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
