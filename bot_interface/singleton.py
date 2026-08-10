"""Ensure only one polling process holds the platform bot token."""
from __future__ import annotations

import atexit
import os
import time
from pathlib import Path

_LOCK_FH = None


def acquire_bot_singleton(lock_dir: str | None = None) -> Path:
    """Exclusive lock so two platform processes cannot both call getUpdates.

    Raises SystemExit if another instance already holds the lock.
    """
    global _LOCK_FH
    base = Path(lock_dir or os.getenv("OUTPUT_DIR") or "/tmp")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path("/tmp")
    lock_path = base / ".ai_agent_7h_bot.poll.lock"
    fh = open(lock_path, "a+", encoding="utf-8")
    try:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise SystemExit(
            "Another AI Agent 7h bot process is already polling this token "
            f"(lock={lock_path}). Stop the other replica/instance first."
        )
    except ImportError:
        # Windows / no fcntl — best-effort pid file
        if lock_path.exists():
            try:
                old = lock_path.read_text(encoding="utf-8").strip()
                if old.isdigit() and int(old) != os.getpid():
                    try:
                        os.kill(int(old), 0)
                        fh.close()
                        raise SystemExit(
                            f"Another bot process appears running (pid={old})."
                        )
                    except OSError:
                        pass
            except SystemExit:
                raise
            except Exception:
                pass
    fh.seek(0)
    fh.truncate()
    fh.write(f"{os.getpid()}\n{time.time()}\n")
    fh.flush()
    _LOCK_FH = fh

    def _release() -> None:
        global _LOCK_FH
        try:
            if _LOCK_FH is not None:
                try:
                    import fcntl

                    fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    _LOCK_FH.close()
                except Exception:
                    pass
                _LOCK_FH = None
        except Exception:
            pass

    atexit.register(_release)
    return lock_path


def clear_telegram_webhook(token: str, timeout: float = 12.0) -> bool:
    """deleteWebhook so polling is the only update consumer."""
    token = (token or "").strip()
    if not token:
        return False
    try:
        import json
        import urllib.request

        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False
