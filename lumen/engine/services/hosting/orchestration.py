"""Host runtime orchestration — single entry for starting/stopping hosted bots.

Integrates control plane (HostingService / worker) with isolation backends.

Selection rules (fail-closed):
  * Production / multi-tenant permanent host → Firecracker only.
  * Explicit backend=docker|gvisor|dind allowed only when
    ENVIRONMENT is dev|test and TBE_HOST_ALLOW_WEAK_BACKEND=1.
  * Project metadata host_backend in .lumen_host.json honored only under that gate.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tbe.hosting.orchestration")

_WEAK = frozenset({"docker", "gvisor", "dind"})


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
    if not req or req in {"auto", "permanent", "default"}:
        return "firecracker"
    if req == "firecracker":
        return "firecracker"
    if req in _WEAK:
        if not allow_weak_backend():
            raise RuntimeError(
                f"backend_rejected:{req}: production permanent host requires Firecracker. "
                "Set TBE_HOST_ALLOW_WEAK_BACKEND=1 only in dev/test."
            )
        return req
    raise RuntimeError(f"unknown_host_backend:{req}")


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


def stop_host(deployment_id: str, *, backend: str = "firecracker") -> None:
    dep = (deployment_id or "").strip()
    if not dep:
        return
    b = (backend or "firecracker").strip().lower()
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
