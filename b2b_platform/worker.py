"""RQ worker process: python -m b2b_platform.worker"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("b2b.worker")


def main() -> int:
    url = (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if not url:
        logger.error("REDIS_URL is required for workers")
        return 2
    from redis import Redis
    from rq import Worker, Queue
    name = (os.getenv("RQ_QUEUE_NAME") or "tbe").strip() or "tbe"
    conn = Redis.from_url(url)
    queues = [Queue(name, connection=conn)]
    # Resume interrupted multi-agent generations left mid-flight after a crash.
    try:
        from telegram_bot_engine.services.multi_agent.redis_board import enqueue_pending_resumes
        resumed = enqueue_pending_resumes(limit=int(os.getenv("MULTI_AGENT_RESUME_BOOT_LIMIT") or "20"))
        if resumed:
            logger.info("multi_agent resume boot enqueued=%s", len(resumed))
    except Exception:
        logger.warning("multi_agent resume boot failed", exc_info=True)

    logger.info("starting RQ worker queue=%s", name)
    Worker(queues, connection=conn).work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
