"""Project Manifest — full architecture document for one hosted bot.

Written to ``.lumen_project_manifest.json`` under the project root and mirrored
on HostInstance fields for control-plane queries.

Schema (v1):
  id, platform, backend, entry_point
  resources: {cpu, memory_mb, disk_mb}
  networking: {public_base_url, webhook_url, internal_port, ingress}
  storage: {data, logs, static, sandbox_root}
  lifecycle: {status, version_ref, deployment_id}
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.project_manifest")

MANIFEST_NAME = ".lumen_project_manifest.json"
SCHEMA_VERSION = 1


@dataclass
class ResourceSpec:
    cpu: float = 0.5
    memory_mb: int = 256
    disk_mb: int = 512


@dataclass
class NetworkSpec:
    public_base_url: str = ""
    webhook_url: str = ""
    internal_port: int = 0
    ingress: str = "traefik_file"  # traefik_file | caddy | path_api


@dataclass
class StorageSpec:
    data: str = "data/"
    logs: str = "logs/"
    static: str = "static/"
    sandbox_root: str = ""


@dataclass
class ProjectManifest:
    schema_version: int = SCHEMA_VERSION
    instance_id: str = ""
    user_id: int = 0
    platform: str = "telegram"  # telegram | discord | whatsapp
    backend: str = "firecracker"
    entry_point: str = ""
    project_path: str = ""
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    networking: NetworkSpec = field(default_factory=NetworkSpec)
    storage: StorageSpec = field(default_factory=StorageSpec)
    status: str = "unknown"
    version_ref: str = ""
    deployment_id: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def default_resources_from_env() -> ResourceSpec:
    import os

    try:
        cpu = float(os.environ.get("TBE_BOT_CPU") or "0.5")
    except Exception:
        cpu = 0.5
    try:
        mem = int(os.environ.get("TBE_BOT_MEMORY_MB") or os.environ.get("TBE_DOCKER_MEMORY") or "256")
    except Exception:
        mem = 256
    try:
        disk = int(os.environ.get("TBE_BOT_DISK_MB") or "512")
    except Exception:
        disk = 512
    return ResourceSpec(cpu=max(0.1, cpu), memory_mb=max(64, mem), disk_mb=max(64, disk))


def build_manifest_from_instance(inst: Any) -> ProjectManifest:
    res = default_resources_from_env()
    cpu = float(getattr(inst, "cpu_quota", 0) or 0) or res.cpu
    mem = int(getattr(inst, "memory_mb", 0) or 0) or res.memory_mb
    platform = str(getattr(inst, "platform", "") or "telegram").lower() or "telegram"
    return ProjectManifest(
        instance_id=str(getattr(inst, "instance_id", "") or ""),
        user_id=int(getattr(inst, "user_id", 0) or 0),
        platform=platform,
        backend=str(getattr(inst, "sandbox_backend", "") or "firecracker"),
        entry_point=str(getattr(inst, "entry_point", "") or ""),
        project_path=str(getattr(inst, "project_path", "") or ""),
        resources=ResourceSpec(cpu=cpu, memory_mb=mem, disk_mb=res.disk_mb),
        networking=NetworkSpec(
            public_base_url=str(getattr(inst, "public_base_url", "") or ""),
            webhook_url=str(getattr(inst, "webhook_public_url", "") or ""),
            internal_port=int(getattr(inst, "internal_port", 0) or 0),
            ingress="traefik_file",
        ),
        storage=StorageSpec(
            sandbox_root=str(getattr(inst, "project_path", "") or ""),
        ),
        status=str(getattr(inst, "status", "") or ""),
        version_ref=str(getattr(inst, "version_ref", "") or ""),
        deployment_id=str(getattr(inst, "deployment_id", "") or ""),
        updated_at=time.time(),
    )


def write_manifest(project_path: Path | str, manifest: ProjectManifest) -> Path:
    root = Path(project_path).resolve()
    path = root / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_manifest(project_path: Path | str) -> dict[str, Any]:
    path = Path(project_path).resolve() / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_manifest_for_instance(inst: Any) -> Path | None:
    path = getattr(inst, "project_path", None)
    if not path:
        return None
    man = build_manifest_from_instance(inst)
    return write_manifest(path, man)


__all__ = [
    "ProjectManifest",
    "ResourceSpec",
    "NetworkSpec",
    "StorageSpec",
    "build_manifest_from_instance",
    "write_manifest",
    "load_manifest",
    "write_manifest_for_instance",
    "default_resources_from_env",
    "MANIFEST_NAME",
]
