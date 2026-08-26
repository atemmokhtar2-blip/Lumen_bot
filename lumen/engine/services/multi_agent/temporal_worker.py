"""Temporal worker entrypoint — official temporalio Worker.

  pip install temporalio
  export TEMPORAL_HOST=localhost:7233
  export TEMPORAL_TASK_QUEUE=tbe-generate
  python -m lumen.engine.services.multi_agent.temporal_worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logger = logging.getLogger(__name__)


async def _run() -> None:
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        print("temporalio not installed: pip install temporalio", file=sys.stderr)
        sys.exit(1)

    from .temporal_defs import activity_fns, workflow_classes

    host = (os.getenv("TEMPORAL_HOST") or "localhost:7233").strip()
    namespace = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip()
    queue = (os.getenv("TEMPORAL_TASK_QUEUE") or "tbe-generate").strip()

    client = await Client.connect(host, namespace=namespace)
    worker = Worker(
        client,
        task_queue=queue,
        workflows=workflow_classes(),
        activities=activity_fns(),
    )
    logger.info("Temporal worker started host=%s ns=%s queue=%s", host, namespace, queue)
    await worker.run()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
