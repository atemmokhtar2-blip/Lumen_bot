"""Background ops: log aggregation + backups on a fixed cadence."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("tbe.hosting.ops_scheduler")

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def _log_interval() -> float:
    try:
        return max(30.0, float(os.environ.get("TBE_HOST_LOG_AGGREGATE_INTERVAL") or "120"))
    except Exception:
        return 120.0


def _backup_interval() -> float:
    try:
        from lumen.hosting.backup_manager import interval_hours
        return max(3600.0, interval_hours() * 3600.0)
    except Exception:
        return 6 * 3600.0


def _loop(get_service: Callable) -> None:
    last_backup = 0.0
    while not _stop.is_set():
        try:
            svc = get_service()
            if svc is not None:
                try:
                    from lumen.hosting.log_aggregator import aggregate_all_running
                    aggregate_all_running(svc)
                except Exception:
                    logger.exception("log aggregate failed")
                now = time.time()
                if now - last_backup >= _backup_interval():
                    try:
                        from lumen.hosting.backup_manager import backup_all_running
                        backup_all_running(svc)
                        last_backup = now
                        logger.info("scheduled host backups completed")
                    except Exception:
                        logger.exception("scheduled backup failed")
                # Conversation retention (30d default)
                try:
                    from lumen.platform.conversations import get_conversation_service
                    n = get_conversation_service().purge_expired(days=int(
                        __import__("os").environ.get("LUMEN_CONV_RETENTION_DAYS") or "30"
                    ))
                    if n:
                        logger.info("purged %s expired conversations", n)
                except Exception:
                    logger.debug("conversation purge soft-fail", exc_info=True)
                # Balance lifecycle tick (grace → suspend) + rate any pending usage batches
                try:
                    from lumen.platform.balance_lifecycle import get_balance_lifecycle
                    get_balance_lifecycle().tick()
                except Exception:
                    logger.debug("balance lifecycle tick skipped", exc_info=True)
                try:
                    from lumen.platform.rating_engine import get_rating_engine
                    get_rating_engine().rate_pending(limit=50)
                except Exception:
                    logger.debug("rate_pending skipped", exc_info=True)
                try:
                    from lumen.platform.credits.llm_live import flush_pending_llm_charges
                    flush_pending_llm_charges(limit=50)
                except Exception:
                    logger.debug("flush_pending_llm skipped", exc_info=True)
        except Exception:
            logger.exception("ops scheduler iteration failed")
        _stop.wait(_log_interval())


def start_ops_scheduler(get_service: Callable) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    if (os.environ.get("TBE_HOST_OPS_SCHEDULER") or "1").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(get_service,), name="lumen-host-ops", daemon=True)
    _thread.start()
    logger.info("host ops scheduler started")


def stop_ops_scheduler() -> None:
    _stop.set()


__all__ = ["start_ops_scheduler", "stop_ops_scheduler"]
