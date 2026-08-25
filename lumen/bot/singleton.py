"""Ensure only one polling process holds the platform bot token."""
from __future__ import annotations

import atexit
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("lumen_bot")

_LOCK_FH = None
_MONGO_CLIENT = None
_MONGO_COLLECTION = None
_MONGO_OWNER = ""
_MONGO_RENEW_STOP: threading.Event | None = None


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
        return client["lumen"]


def _lease_seconds() -> int:
    try:
        return max(30, int(os.getenv("TBE_POLL_LEASE_SEC") or "90"))
    except ValueError:
        return 90


def _start_mongo_renewer(coll, owner: str, lease_sec: int) -> None:
    """Keep the distributed lease alive until process exit."""
    global _MONGO_RENEW_STOP
    if _MONGO_RENEW_STOP is not None:
        _MONGO_RENEW_STOP.set()
    stop = threading.Event()
    _MONGO_RENEW_STOP = stop
    interval = max(10.0, lease_sec / 3.0)

    def _loop() -> None:
        while not stop.wait(interval):
            try:
                now = datetime.now(timezone.utc)
                coll.update_one(
                    {"_id": "telegram_polling", "owner": owner},
                    {"$set": {"expires_at": now + timedelta(seconds=lease_sec), "renewed_at": now}},
                )
            except Exception as exc:
                logger.warning("mongo poll lease renew failed: %s", exc)

    th = threading.Thread(target=_loop, name="mongo-poll-lease", daemon=True)
    th.start()


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
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        coll = _resolve_mongo_db(client)["ai_agent_runtime_locks"]
    except (ConfigurationError, PyMongoError, Exception) as exc:
        logger.warning(
            "Mongo polling lock unavailable (%s: %s) — using local file lock",
            type(exc).__name__,
            exc,
        )
        try:
            client.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return None

    try:
        # TTL cleanup of expired leases (safe if index already exists)
        coll.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        pass

    owner = f"{os.uname().nodename}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
    lease_sec = _lease_seconds()
    deadline = time.monotonic() + max(5.0, float(wait_seconds))
    forced = False

    while True:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_sec)
        try:
            # Take lock if missing, expired, already ours, or force after wait
            filt: dict = {"_id": "telegram_polling"}
            if not forced:
                filt = {
                    "_id": "telegram_polling",
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"expires_at": {"$exists": False}},
                        {"owner": owner},
                    ],
                }
            doc = coll.find_one_and_update(
                filt,
                {
                    "$set": {
                        "owner": owner,
                        "expires_at": lease_until,
                        "acquired_at": now,
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            if doc and doc.get("owner") == owner:
                _MONGO_CLIENT, _MONGO_COLLECTION, _MONGO_OWNER = client, coll, owner
                _start_mongo_renewer(coll, owner, lease_sec)

                def _release_mongo() -> None:
                    global _MONGO_CLIENT, _MONGO_COLLECTION, _MONGO_OWNER, _MONGO_RENEW_STOP
                    try:
                        if _MONGO_RENEW_STOP is not None:
                            _MONGO_RENEW_STOP.set()
                        if _MONGO_COLLECTION is not None and _MONGO_OWNER:
                            _MONGO_COLLECTION.delete_one(
                                {"_id": "telegram_polling", "owner": _MONGO_OWNER}
                            )
                        if _MONGO_CLIENT is not None:
                            _MONGO_CLIENT.close()
                    finally:
                        _MONGO_CLIENT = _MONGO_COLLECTION = None
                        _MONGO_OWNER = ""
                        _MONGO_RENEW_STOP = None

                atexit.register(_release_mongo)
                logger.info(
                    "Acquired distributed Telegram polling lease (owner=%s lease=%ss force=%s)",
                    owner,
                    lease_sec,
                    forced,
                )
                return Path(f"mongodb://telegram_polling/{owner}")
        except DuplicateKeyError:
            pass
        except Exception as exc:
            logger.warning("mongo lock attempt failed: %s", exc)

        if time.monotonic() >= deadline:
            # Railway single-replica rolling deploys: previous instance often dies
            # without releasing a long lease. After waiting, take over once.
            if not forced:
                existing = None
                try:
                    existing = coll.find_one({"_id": "telegram_polling"})
                except Exception:
                    existing = None
                logger.warning(
                    "Polling lease busy (%s) — forcing takeover after %.0fs wait",
                    (existing or {}).get("owner"),
                    wait_seconds,
                )
                forced = True
                # one more immediate attempt with force
                continue
            try:
                client.close()
            except Exception:
                pass
            raise SystemExit(
                "Another bot replica owns the distributed Telegram polling lease "
                "(set replicas=1; lease auto-expires in ~"
                f"{lease_sec}s and renews while the owner is alive)"
            )
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
        raise SystemExit(
            "TBE_MULTI_REPLICA requires MONGODB_URI/MONGO_URI for a cross-host polling lease"
        )
    # Durable lock dir — never rely on /tmp alone (systemd tmpfiles.d wipes it)
    base = Path(
        lock_dir
        or os.getenv("RUNTIME_LOCK_DIR")
        or os.getenv("STATE_DIR")
        or os.getenv("OUTPUT_DIR")
        or ""
    )
    if not str(base):
        # project-local fallback then /var/lib
        for candidate in (
            Path(__file__).resolve().parents[1] / ".runtime",
            Path("/var/lib/lumen"),
            Path.home() / ".lumen",
        ):
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                base = candidate
                break
            except OSError:
                continue
        else:
            base = Path("/tmp/lumen")
            base.mkdir(parents=True, exist_ok=True)
    else:
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path.home() / ".lumen"
            base.mkdir(parents=True, exist_ok=True)

    lock_path = base / ".lumen_bot.poll.lock"
    deadline = time.monotonic() + max(5.0, float(wait_seconds))
    last_err = ""

    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # exists but not ours — treat as alive
            return True
        except OSError:
            return False

    def _read_lock_pid(path: Path) -> int | None:
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            if lines and lines[0].strip().isdigit():
                return int(lines[0].strip())
        except Exception:
            return None
        return None

    def _break_stale_lock(path: Path) -> bool:
        """If lock file names a dead PID, remove it so flock can be re-acquired.

        Kernel releases flock on process death; residual lock *files* on some
        filesystems or after unclean exits still confuse operators — clear them
        when the recorded PID is gone.
        """
        pid = _read_lock_pid(path)
        if pid is None:
            try:
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except TypeError:
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    return False
            except OSError:
                return False
            return True
        if _pid_alive(pid):
            return False
        logger.warning("Stale poll lock: pid=%s is dead — removing %s", pid, path)
        try:
            path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            try:
                path.unlink()
            except OSError:
                return False
        except OSError:
            return False
        return True

    while True:
        # Proactively clear stale lock file before open/flock
        if lock_path.exists():
            _break_stale_lock(lock_path)

        fh = open(lock_path, "a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n{time.time()}\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
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
                # Remove lock file on clean exit so restart never sees a ghost PID
                try:
                    lock_path.unlink(missing_ok=True)  # type: ignore[call-arg]
                except TypeError:
                    try:
                        if lock_path.exists():
                            lock_path.unlink()
                    except OSError:
                        pass
                except OSError:
                    pass

            atexit.register(_release)
            return lock_path
        except BlockingIOError:
            try:
                fh.close()
            except Exception:
                pass
            # Holder may have died between open and our flock attempt
            if _break_stale_lock(lock_path):
                continue
            holder = _read_lock_pid(lock_path)
            if time.monotonic() >= deadline:
                raise SystemExit(
                    "Another Lumen bot process is still polling "
                    f"(lock={lock_path}, holder_pid={holder}). "
                    f"Set replicas=1 and restart once. waited={wait_seconds:.0f}s"
                )
            time.sleep(1.0)
            continue
        except ImportError:
            # No fcntl (rare) — PID file only with liveness check
            try:
                old_pid = _read_lock_pid(lock_path)
            except Exception:
                old_pid = None
            if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
                try:
                    fh.close()
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    raise SystemExit(
                        f"Another bot process appears running (pid={old_pid})."
                    )
                time.sleep(1.0)
                continue
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
            headers={"User-Agent": "Lumen/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False
