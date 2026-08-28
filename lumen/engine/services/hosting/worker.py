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
    """Worker node bootstrap — permanent host plane (Firecracker-first)."""
    from lumen.engine.services.hosting.pg_control_plane import migrate, is_postgres
    if not is_postgres():
        raise RuntimeError("Worker requires TBE_DATABASE_URL=postgresql://...")
    migrate()

    # Production isolation: Firecracker + jailer must be available on worker nodes
    os.environ.setdefault("TBE_MULTI_TENANT", "1")
    if (os.environ.get("ENVIRONMENT") or "").strip().lower() in {"", "development", "dev", "test"}:
        # worker nodes are production by default
        os.environ.setdefault("ENVIRONMENT", "production")

    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    probe = FirecrackerSandboxBackend().probe()
    if not probe.available:
        raise RuntimeError(
            f"worker_requires_firecracker:{probe.reason}. "
            "Install firecracker+jailer+kernel+rootfs (see deploy/firecracker/)."
        )
    logger.info("firecracker probe ok strength=%s", probe.strength)

    from lumen.engine.services.hosting.network import ensure_network, telegram_egress_hint
    ok, msg = ensure_network()
    if not ok:
        logger.warning("docker-network setup skipped/failed (FC uses TAP): %s", msg)
    else:
        logger.info("network %s", msg)
    logger.info(telegram_egress_hint())

    # Docker registry only needed for legacy docker backend workers
    if (os.environ.get("TBE_WORKER_ALLOW_DOCKER_REGISTRY") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        from lumen.engine.services.hosting.registry import docker_login, registry_host
        if registry_host():
            ok, msg = docker_login()
            if not ok:
                raise RuntimeError(f"registry_login_failed:{msg}")
            logger.info("registry %s", msg)

    from lumen.engine.services.hosting.fleet import FleetRegistry
    rec = FleetRegistry().register(version=os.environ.get("TBE_WORKER_VERSION") or "1")
    logger.info(
        "registered FC worker %s max_bots=%s backend=firecracker",
        rec.node_id,
        rec.max_bots,
    )


def _meta(job) -> dict:
    try:
        return json.loads(job.meta_json or "{}")
    except Exception:
        return {}


def process_one(queue=None, fleet=None) -> bool:
    from lumen.engine.services.hosting.capacity import local_node_capacity, node_id
    from lumen.engine.services.hosting.deploy_queue import get_deploy_queue
    from lumen.engine.services.crypto_tokens import unseal_token
    from lumen.engine.services.hosting.artifacts import (
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

        # Single production path: sandbox_runtime (never bare LocalProcess)
        os.environ.setdefault("TBE_WORKER_BUILD", "1")
        try:
            from lumen.engine.services.sandbox_runtime import start_sandboxed_bot
            backend, handle = start_sandboxed_bot(
                project_path=build_path,
                bot_token=token,
                user_id=int(job.user_id),
                service_name=f"user-{job.user_id}",
                env_vars={"BOT_TOKEN": token, "TELEGRAM_BOT_TOKEN": token},
            )
            if handle.ok and handle.status == "running":
                q.mark_running(
                    job.job_id,
                    deployment_id=handle.deployment_id or "",
                    image_tag=str((handle.meta or {}).get("runtime") or backend.name),
                )
                logger.info(
                    "job %s running backend=%s dep=%s",
                    job.job_id, backend.name, handle.deployment_id,
                )
            else:
                q.mark_failed(
                    job.job_id,
                    (handle.message or f"sandbox_failed:{backend.name}")[:500],
                )
        except Exception as sbx_exc:
            q.mark_failed(job.job_id, f"sandbox:{type(sbx_exc).__name__}:{sbx_exc}"[:500])
            return True
    except Exception as e:
        logger.exception("job %s failed", job.job_id)
        try:
            from lumen.engine.services.sentry_ops import capture_exception
            capture_exception(e, job_id=job.job_id, user_id=job.user_id)
        except Exception:
            pass
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
    from lumen.engine.services.hosting.fleet import FleetRegistry
    from lumen.engine.services.hosting.deploy_queue import get_deploy_queue
    fleet = FleetRegistry()
    q = get_deploy_queue()
    logger.info("worker loop node=%s", os.environ.get("TBE_NODE_ID") or "")
    try:
        while True:
            try:
                fleet.sweep_stale()
                try:
                    from lumen.engine.services.sandbox_runtime.supervisor import supervisor_tick
                    tick = supervisor_tick()
                    if tick.get("reaped") or tick.get("lifetime_killed"):
                        logger.info("supervisor tick %s", tick)
                except Exception:
                    logger.debug("supervisor tick skipped", exc_info=True)

                try:
                    from lumen.platform.rating_engine import get_rating_engine
                    rated = get_rating_engine().rate_pending(limit=50)
                    if rated.get("processed") or rated.get("failed"):
                        logger.info("rating tick %s", rated)
                except Exception:
                    logger.debug("rating tick skipped", exc_info=True)
                try:
                    from lumen.platform.balance_lifecycle import get_balance_lifecycle
                    lc = get_balance_lifecycle().tick()
                    if lc.get("actions"):
                        logger.info("balance lifecycle %s", lc)
                except Exception:
                    logger.debug("balance lifecycle tick skipped", exc_info=True)
                worked = process_one(queue=q, fleet=fleet)
                if not worked:
                    try:
                        from lumen.engine.services.hosting.capacity import node_id
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
