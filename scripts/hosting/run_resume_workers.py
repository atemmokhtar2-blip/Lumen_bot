#!/usr/bin/env python3
"""Deprecated — cross-process HITL resume is now handled by the LangGraph
SqliteSaver checkpoint in lumen.engine.services.multi_agent.langgraph_pipeline.
runner.resume_langgraph_hitl().

This script previously drained a "redis_board" module that never existed in the
codebase.  It has been reduced to a no-op that logs the deprecation notice so
any hosting cron-job referencing it does not crash.
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("resume_workers")


def main() -> None:
    logger.warning(
        "run_resume_workers is deprecated — HITL resume is now durable via "
        "LangGraph SqliteSaver (resume_langgraph_hitl). No action taken."
    )


if __name__ == "__main__":
    main()
