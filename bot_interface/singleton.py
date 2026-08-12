"""Ensure only one polling process holds the platform bot token."""
from __future__ import annotations

import atexit
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LOCK_FH = None
_MONGO_CLIENT = None
_MONGO_COLLECTION = None
_MONGO_OWNER = ""


def _resolve_mongo_db(client):
    """Pick DB name without requiring it in the URI path (Railway-safe)."""
    name = (
        os.getenv("MONGODB_DB")
        or os.getenv("MONGO_DB")
        or os.getenv("MONGODB_DATABASE")
        or ""
    ).strip()
    if name:
        return client[name]
    try:
        return client.get_default_database()
    except Exception:
        # URI has no /dbname — same default as mongo_users.py
        return client["ai_agent_7h"]


def _try_acquire_mongo_lock(*, wait_seconds: float) -> Path | None:
    """Acquire a cross-host lease when Mongo is configured; return None if unused."""
    global _MONGO_CLIENT, _MONGO_COLLECTION, _MONGO_OWNER
    uri = (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
    if not uri:
        return None
    try:
        from pymongo import MongoClient, ReturnDocument
        from pymongo.errors import DuplicateKeyError, ConfigurationError, PyMongoError
    except ImportError as exc:
        raise SystemExit("MONGODB_URI is configured but pymongo is missing") from exc
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        coll = _resolve_mongo_db(client)["ai_agent_runtime_locks"]
    except (ConfigurationError, PyMongoError, Exception) as exc:
        # Misconfigured URI must not crash the whole bot — fall back to file lock
        import logging
        logging.getLogger("ai_agent_7h_bot").warning(
            "Mongo polling lock unavailable (%s: %s) — using local file lock",
            type(exc).__name__,
            exc,
        )
        try:
            client.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return None
    coll.create_index("expires_at", expireAfterSeconds=0)
    owner = f"{os.uname().nodename}:{os.getpid()}:{uuid.uuid4().hex}"
    deadline = time.monotonic() + max(5.0, float(wait_seconds))
    while True:
        now = datetime.now(timezone.utc)
        lease = now + timedelta(hours=2)
        try:
            doc = coll.find_one_and_update(
                {"_id": "telegram_polling", "$or": [{"expires_at": {"$lte": now}}, {"owner": owner}]},
                {"$set": {"owner": owner, "expires_at": lease}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            if doc and doc.get("owner") == owner:
                _MONGO_CLIENT, _MONGO_COLLECTION, _MONGO_OWNER = client, coll, owner
                lock_path = Path(f"mongodb://telegram_polling/{owner}")
                def _release_mongo() -> None:
                    global _MONGO_CLIENT, _MONGO_COLLECTION, _MONGO_OWNER
                    try:
                        if _MONGO_COLLECTION is not None and _MONGO_OWNER:
                            _MONGO_COLLECTION.delete_one({"_id": "telegram_polling", "owner": _MONGO_OWNER})
                        if _MONGO_CLIENT is not None:
                            _MONGO_CLIENT.close()
                    finally:
                        _MONGO_CLIENT = _MONGO_COLLECTION = None
                        _MONGO_OWNER = ""
                atexit.register(_release_mongo)
                return lock_path
        except DuplicateKeyError:
            pass
        if time.monotonic() >= deadline:
            client.close()
            raise SystemExit("Another bot replica owns the distributed Telegram polling lease")
        time.sleep(1.0)



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
    distributed = _try_acquire_mongo_lock(wait_seconds=wait_seconds)
    if distributed is not None:
        return distributed
    if os.getenv("TBE_MULTI_REPLICA", "0").strip().lower() in {"1", "true", "yes", "on"} and os.getenv("TBE_ALLOW_LOCAL_SINGLETON", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("TBE_MULTI_REPLICA requires MONGODB_URI/MONGO_URI for a cross-host polling lease")
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
