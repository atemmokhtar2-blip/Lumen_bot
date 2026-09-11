"""Host runtime orchestration — single entry for starting/stopping hosted bots.

Integrates control plane (HostingService / worker) with isolation backends.

Selection rules (fail-closed):
  * Production / multi-tenant permanent host → Firecracker by default.
  * Explicit TBE_HOST_BACKEND=lumen_serverless → Lumen-owned serverless host
    (internal platform account; end users never see vendor names).
  * Explicit backend=docker|gvisor|dind allowed only when
    ENVIRONMENT is dev|test and TBE_HOST_ALLOW_WEAK_BACKEND=1.
  * Project metadata host_backend in .lumen_host.json honored under the same gates.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tbe.hosting.orchestration")

_WEAK = frozenset({"docker", "gvisor", "dind"})
_SERVERLESS = frozenset({"lumen_serverless", "serverless"})


def _env_name() -> str:
    return (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()


def is_production_path() -> bool:
    if _env_name() in {"dev", "development", "local", "test"}:
        return False
    multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower()
    return multi in {"1", "true", "yes", "on", ""}


def allow_weak_backend() -> bool:
    if is_production_path():
        return False
    return (os.environ.get("TBE_HOST_ALLOW_WEAK_BACKEND") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def project_backend_preference(project_path: str | Path) -> str:
    try:
        p = Path(project_path) / ".lumen_host.json"
        if not p.is_file():
            return ""
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("host_backend") or data.get("backend") or "").strip().lower()
    except Exception:
        return ""


def resolve_backend_name(*, project_path: str = "", requested: str = "") -> str:
    req = (requested or project_backend_preference(project_path) or "").strip().lower()
    env_req = (os.environ.get("TBE_HOST_BACKEND") or "").strip().lower()
    if not req:
        req = env_req
    # Normalize aliases (internal only — never shown to users)
    if req in {"vercel"}:
        req = "lumen_serverless"
    if not req or req in {"auto", "permanent", "default"}:
        return "firecracker"
    if req == "firecracker":
        return "firecracker"
    if req in _SERVERLESS:
        return "lumen_serverless"
    if req in _WEAK:
        if not allow_weak_backend():
            raise RuntimeError(
                f"backend_rejected:{req}: production permanent host requires Firecracker "
                "or lumen_serverless. Set TBE_HOST_ALLOW_WEAK_BACKEND=1 only in dev/test."
            )
        return req
    raise RuntimeError(f"unknown_host_backend:{req}")


def _serverless_available() -> tuple[bool, str]:
    try:
        from lumen.engine.services.live_deployment.vercel_client import token_configured
        if token_configured():
            return True, "token_ok"
        return False, "platform_host_token_missing"
    except Exception as exc:
        return False, type(exc).__name__


def start_host(
    *,
    project_path: str,
    bot_token: str,
    user_id: int = 0,
    service_name: str = "",
    env_vars: Optional[dict[str, str]] = None,
    backend: str = "",
) -> tuple[Any, Any]:
    name = resolve_backend_name(project_path=project_path, requested=backend)
    logger.info("host orchestration backend=%s user=%s", name, user_id)

    if name == "lumen_serverless":
        return _start_serverless(
            project_path=project_path,
            bot_token=bot_token,
            user_id=user_id,
            service_name=service_name,
            env_vars=env_vars,
        )

    if name == "firecracker":
        from lumen.engine.services.sandbox_runtime import start_permanent_host_bot

        return start_permanent_host_bot(
            project_path=project_path,
            bot_token=bot_token,
            user_id=user_id,
            service_name=service_name,
            env_vars=env_vars,
        )

    from lumen.engine.services.sandbox_runtime import start_sandboxed_bot

    os.environ["TBE_SANDBOX_BACKEND"] = name
    return start_sandboxed_bot(
        project_path=project_path,
        bot_token=bot_token,
        user_id=user_id,
        service_name=service_name,
        env_vars=env_vars,
    )


class _ServerlessBackend:
    name = "lumen_serverless"


def _start_serverless(
    *,
    project_path: str,
    bot_token: str,
    user_id: int,
    service_name: str,
    env_vars: Optional[dict[str, str]],
) -> tuple[Any, Any]:
    from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver
    from lumen.engine.services.sandbox_runtime.types import SandboxHandle

    ok, reason = _serverless_available()
    if not ok:
        handle = SandboxHandle(
            backend="lumen_serverless",
            deployment_id="",
            status="failed",
            message="الاستضافة غير مُعدّة على خوادم Lumen.",
            meta={"reason": reason},
        )
        return _ServerlessBackend(), handle

    # Phase 2: webhook adapter before upload (idempotent)
    try:
        from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_serverless
        prepared = prepare_project_for_serverless(project_path)
        if not prepared.ok:
            handle = SandboxHandle(
                backend="lumen_serverless",
                deployment_id="",
                status="failed",
                message=prepared.message or "فشل تجهيز المشروع",
                meta={"prepare": dict(prepared.details or {})},
            )
            return _ServerlessBackend(), handle
        prepare_meta = dict(prepared.details or {})
        webhook_path = str(prepare_meta.get("webhook_path") or "/api")
    except Exception as prep_exc:
        logger.warning("serverless prepare failed: %s", type(prep_exc).__name__)
        handle = SandboxHandle(
            backend="lumen_serverless",
            deployment_id="",
            status="failed",
            message="فشل تجهيز المشروع لاستضافة Lumen",
            meta={"error": type(prep_exc).__name__},
        )
        return _ServerlessBackend(), handle

    env = dict(env_vars or {})
    if bot_token:
        env.setdefault("BOT_TOKEN", bot_token)
        env.setdefault("TELEGRAM_BOT_TOKEN", bot_token)

    svc = (service_name or f"lumen-u{int(user_id) or 0}-bot").strip()
    driver = VercelProcessDriver()
    st = driver.deploy(project_path, env_vars=env, service_name=svc)

    status = (st.status or "").lower()
    if status in {"running", "deploy_running", "success"}:
        mapped = "running"
    elif status in {"pending", "building", "deploying"}:
        mapped = "starting"
    else:
        mapped = "failed"

    handle = SandboxHandle(
        backend="lumen_serverless",
        deployment_id=str(st.deployment_id or ""),
        container_or_vm_id=str(st.project_id or ""),
        status=mapped,
        message=str(st.message or "")[:500],
        meta={
            "url": st.url,
            "project_id": st.project_id,
            "provider": "lumen_serverless",
            "service_id": st.service_id,
            "webhook_path": webhook_path,
            "webhook_url": (str(st.url).rstrip("/") + webhook_path) if st.url else "",
            "prepare": prepare_meta,
        },
    )
    return _ServerlessBackend(), handle


def stop_host(deployment_id: str, *, backend: str = "firecracker") -> None:
    dep = (deployment_id or "").strip()
    if not dep:
        return
    b = (backend or "firecracker").strip().lower()
    if b in _SERVERLESS or b == "vercel":
        try:
            from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver
            VercelProcessDriver().stop(dep)
        except Exception as exc:
            logger.warning("serverless stop failed: %s", type(exc).__name__)
        return
    if b == "firecracker" or dep.startswith("fc-"):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        FirecrackerSandboxBackend().stop(dep)
        return
    if allow_weak_backend():
        from lumen.engine.services.sandbox_runtime import select_sandbox_backend
        backend_obj, _ = select_sandbox_backend(require_available=False)
        backend_obj.stop(dep)


__all__ = [
    "resolve_backend_name",
    "start_host",
    "stop_host",
    "is_production_path",
    "allow_weak_backend",
    "project_backend_preference",
]
