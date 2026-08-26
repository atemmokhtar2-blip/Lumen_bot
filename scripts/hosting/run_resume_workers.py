#!/usr/bin/env python3
"""Phase B — drain resumable multi-agent jobs (file/Redis board + worker pool).

  MULTI_AGENT_RESUME_USE_POOL=1
  python scripts/hosting/run_resume_workers.py --loop --interval 30
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("resume_workers")


def once(limit: int) -> list:
    from lumen.engine.services.multi_agent.redis_board import scan_and_resume
    return scan_and_resume(limit=limit)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--loop", action="store_true")
    p.add_argument("--interval", type=float, default=30.0)
    args = p.parse_args()
    if not args.loop:
        results = once(args.limit)
        for r in results:
            logger.info("%s", r)
        return
    while True:
        try:
            results = once(args.limit)
            logger.info("drained=%s results=%s", len(results), results[:5])
        except Exception:
            logger.exception("resume drain failed")
        time.sleep(max(5.0, args.interval))


if __name__ == "__main__":
    main()
