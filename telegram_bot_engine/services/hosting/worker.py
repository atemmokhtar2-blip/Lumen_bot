"""Host worker for commercial fleet — artifact-based multi-node builds.

Workers never need the API host's local project_path. They fetch a packaged
artifact (S3 or shared TBE_ARTIFACT_ROOT), extract, build, push, run.
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger("tbe.hosting.worker")


def bootstrap() -> None:
    from telegram_bot_engine.services.hosting.pg_control_plane import migrate, is_postgres
    if not is_postgres():
        raise RuntimeError("Worker requires TBE_DATABASE_URL=postgresql://...")
    migrate()

    from telegram_bot_engine.services.hosting.network import ensure_network, telegram_egress_hint
    ok, msg = ensure_network()
    if not ok:
        raise RuntimeError(f"network_setup_failed:{msg}")
    logger.info("network %s", msg)
    logger.info(telegram_egress_hint())

    from telegram_bot_engine.services.hosting.registry import docker_login, registry_host
    if registry_host():
        ok, msg = docker_login()
        if not ok:
            raise RuntimeError(f"registry_login_failed:{msg}")
        logger.info("registry %s", msg)

    from telegram_bot_engine.services.hosting.fleet import FleetRegistry
    rec = FleetRegistry().register(version=os.environ.get("TBE_WORKER_VERSION") or "1")
    logger.info("registered worker %s max_bots=%s", rec.node_id, rec.max_bots)


def _meta(job) -> dict:
    try:
        return json.loads(job.meta_json or "{}")
    except Exception:
        return {}


def process_one(queue=None, fleet=None) -> bool:
    from telegram_bot_engine.services.hosting.capacity import local_node_capacity, node_id
    from telegram_bot_engine.services.hosting.deploy_queue import get_deploy_queue
    from telegram_bot_engine.services.crypto_tokens import unseal_token
    from telegram_bot_engine.services.hosting.artifacts import (
        fetch_artifact,
        extract_artifact,
        cleanup_work,
    )

    q = queue or get_deploy_queue()
    nid = node_id()
    running = q.count_running_on_node(nid)
    if fleet is not None:
        try:
            fleet.heartbeat(running_bots=running)
        except Exception:
            logger.exception("fleet heartbeat failed")

    cap = local_node_capacity(running=running)
    if not cap.can_accept:
        logger.info("node %s at capacity running=%s max=%s", nid, running, cap.max_bots)
        return False

    job = q.claim_next(nid)
    if not job:
        return False

    q.update(job.job_id, status="building")
    if hasattr(q, "heartbeat"):
        q.heartbeat(job.job_id)

    token = unseal_token(job.sealed_token)
    if not token:
        q.mark_failed(job.job_id, "token_unseal_failed")
        return True

    meta = _meta(job)
    artifact_uri = (meta.get("artifact_uri") or "").strip()
    artifact_key = (meta.get("artifact_job_key") or job.job_id).strip()
    work_id = job.job_id

    try:
        if not artifact_uri:
            # Legacy jobs: require path on this node (single-host only)
            build_path = job.project_path
            if not build_path or not __import__("pathlib").Path(build_path).is_dir():
                q.mark_failed(job.job_id, "artifact_uri_missing_and_path_unavailable")
                return True
        else:
            zpath = fetch_artifact(artifact_uri, artifact_key)
            build_path = str(extract_artifact(zpath, work_id))

        from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
            DockerProcessDriver,
            docker_available,
        )
        if not docker_available():
            q.mark_failed(job.job_id, "docker_unavailable")
            return True

        # sandbox path check expects OUTPUT_DIR/users — extracted work may be under artifacts/
        # Temporarily allow by setting path under a users-like tree or relax via env for workers
        os.environ.setdefault("TBE_WORKER_BUILD", "1")

        driver = DockerProcessDriver()
        st = driver.deploy(
            build_path,
            env_vars={"BOT_TOKEN": token, "TELEGRAM_BOT_TOKEN": token},
            service_name=f"user-{job.user_id}",
        )
        status = str(getattr(st, "status", "") or "")
        if status == "running":
            q.mark_running(
                job.job_id,
                deployment_id=getattr(st, "deployment_id", "") or "",
                image_tag=str(getattr(st, "service_id", "") or ""),
            )
            logger.info("job %s running dep=%s", job.job_id, getattr(st, "deployment_id", ""))
        else:
            q.mark_failed(job.job_id, getattr(st, "message", "deploy_failed")[:500])
    except Exception as e:
        logger.exception("job %s failed", job.job_id)
        q.mark_failed(job.job_id, f"{type(e).__name__}:{e}")
    finally:
        try:
            cleanup_work(work_id)
        except Exception:
            pass
    return True


def run_forever(poll_seconds: float | None = None) -> None:
    poll = float(poll_seconds or os.environ.get("TBE_WORKER_POLL_SECONDS") or 2)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bootstrap()
    from telegram_bot_engine.services.hosting.fleet import FleetRegistry
    from telegram_bot_engine.services.hosting.deploy_queue import get_deploy_queue
    fleet = FleetRegistry()
    q = get_deploy_queue()
    logger.info("worker loop node=%s", os.environ.get("TBE_NODE_ID") or "")
    try:
        while True:
            try:
                fleet.sweep_stale()
                worked = process_one(queue=q, fleet=fleet)
                if not worked:
                    try:
                        from telegram_bot_engine.services.hosting.capacity import node_id
                        fleet.heartbeat(running_bots=q.count_running_on_node(node_id()))
                    except Exception:
                        pass
                    time.sleep(poll)
            except Exception:
                logger.exception("worker loop error")
                time.sleep(poll)
    except KeyboardInterrupt:
        logger.info("worker shutting down")
        try:
            fleet.mark_offline()
        except Exception:
            pass


if __name__ == "__main__":
    run_forever()
