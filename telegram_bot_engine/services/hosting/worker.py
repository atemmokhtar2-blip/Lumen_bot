"""Host worker: claims deploy jobs and runs image-based Docker deploys.

Run as a separate process on each node:
  python -m telegram_bot_engine.services.hosting.worker

Many workers across many nodes = path to 20k hosted bots.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("tbe.hosting.worker")


def process_one(queue=None) -> bool:
    """Claim and process a single job. Returns True if a job was handled."""
    from telegram_bot_engine.services.hosting.capacity import local_node_capacity, node_id
    from telegram_bot_engine.services.hosting.deploy_queue import get_deploy_queue
    from telegram_bot_engine.services.crypto_tokens import unseal_token

    q = queue or get_deploy_queue()
    nid = node_id()
    running = q.count_running_on_node(nid)
    cap = local_node_capacity(running=running)
    if not cap.can_accept:
        logger.info("node %s at capacity running=%s max=%s", nid, running, cap.max_bots)
        return False

    job = q.claim_next(nid)
    if not job:
        return False

    q.update(job.job_id, status="building")
    token = unseal_token(job.sealed_token)
    if not token:
        q.mark_failed(job.job_id, "token_unseal_failed")
        return True

    try:
        from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
            DockerProcessDriver,
            docker_available,
        )
        if not docker_available():
            q.mark_failed(job.job_id, "docker_unavailable")
            return True
        driver = DockerProcessDriver()
        st = driver.deploy(
            job.project_path,
            env_vars={"BOT_TOKEN": token, "TELEGRAM_BOT_TOKEN": token},
            service_name=f"user-{job.user_id}",
        )
        status = str(getattr(st, "status", "") or "")
        if status == "running":
            q.mark_running(
                job.job_id,
                deployment_id=getattr(st, "deployment_id", "") or "",
                image_tag=getattr(st, "service_id", "") or "",
            )
            # Best-effort: register in host service store if available
            try:
                from telegram_bot_engine.services.hosting.service import get_hosting_service
                # HostingService.start already used for sync path; worker updates queue only
            except Exception:
                pass
            logger.info("job %s running dep=%s", job.job_id, getattr(st, "deployment_id", ""))
        else:
            q.mark_failed(job.job_id, getattr(st, "message", "deploy_failed")[:500])
    except Exception as e:
        logger.exception("job %s failed", job.job_id)
        q.mark_failed(job.job_id, f"{type(e).__name__}:{e}")
    return True


def run_forever(poll_seconds: float | None = None) -> None:
    poll = float(poll_seconds or os.environ.get("TBE_WORKER_POLL_SECONDS") or 2)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.info("host worker starting node=%s", os.environ.get("TBE_NODE_ID") or "")
    while True:
        try:
            worked = process_one()
            if not worked:
                time.sleep(poll)
        except KeyboardInterrupt:
            logger.info("worker stop")
            break
        except Exception:
            logger.exception("worker loop error")
            time.sleep(poll)


if __name__ == "__main__":
    run_forever()
