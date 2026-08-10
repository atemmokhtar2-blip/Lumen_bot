"""Ensure only one polling process holds the platform bot token."""
from __future__ import annotations

import atexit
import os
import time
from pathlib import Path

_LOCK_FH = None


def acquire_bot_singleton(
    lock_dir: str | None = None,
    *,
    wait_seconds: float = 45.0,
) -> Path:
    """Exclusive lock so two platform processes cannot both call getUpdates.

    Waits for a previous instance to release the lock (rolling deploys),
    instead of exiting immediately — that was leaving the bot dead.
    """
    global _LOCK_FH
    base = Path(lock_dir or os.getenv("OUTPUT_DIR") or "/tmp")
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path("/tmp")
    lock_path = base / ".ai_agent_7h_bot.poll.lock"
    deadline = time.monotonic() + max(5.0, float(wait_seconds))
    last_err = ""

    while True:
        fh = open(lock_path, "a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # acquired
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
                            import fcntl as _fc

                            _fc.flock(_LOCK_FH.fileno(), _fc.LOCK_UN)
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
        except BlockingIOError:
            last_err = "lock_held"
            try:
                fh.close()
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise SystemExit(
                    "Another AI Agent 7h bot process is still polling "
                    f"(lock={lock_path}). Set replicas=1 and restart once. "
                    f"waited={wait_seconds:.0f}s"
                )
            time.sleep(1.0)
            continue
        except ImportError:
            # no fcntl — pid-file best effort
            try:
                old = lock_path.read_text(encoding="utf-8").strip().splitlines()
                old_pid = int(old[0]) if old and old[0].isdigit() else None
            except Exception:
                old_pid = None
            if old_pid and old_pid != os.getpid():
                try:
                    os.kill(old_pid, 0)
                    if time.monotonic() >= deadline:
                        fh.close()
                        raise SystemExit(
                            f"Another bot process appears running (pid={old_pid})."
                        )
                    fh.close()
                    time.sleep(1.0)
                    continue
                except OSError:
                    pass
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n{time.time()}\n")
            fh.flush()
            _LOCK_FH = fh
            return lock_path
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
            try:
                fh.close()
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise SystemExit(f"Could not acquire poll lock: {last_err}")
            time.sleep(1.0)


def clear_telegram_webhook(token: str, timeout: float = 12.0) -> bool:
    """deleteWebhook so polling is the only update consumer."""
    token = (token or "").strip()
    if not token:
        return False
    try:
        import json
        import urllib.request

        url = (
            f"https://api.telegram.org/bot{token}/"
            "deleteWebhook?drop_pending_updates=true"
        )
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "AI-Agent-7h/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False
