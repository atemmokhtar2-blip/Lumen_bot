"""Deploy versioning for hosted projects — real rollback, not just a git sha string.

On each permanent-host prepare/start:
  1) git snapshot → version_ref (sha)
  2) package zip → artifacts store keyed by version_ref
  3) index under project_id for list/restore

Restore:
  extract artifact over project path (caller stops instance first).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.versions")


def _index_path(project_path: Path) -> Path:
    return project_path / ".lumen_host_versions.json"


def _load_index(project_path: Path) -> list[dict[str, Any]]:
    p = _index_path(project_path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(data.get("versions") or [])
    except Exception:
        return []


def _save_index(project_path: Path, versions: list[dict[str, Any]]) -> None:
    p = _index_path(project_path)
    payload = {"versions": versions[-50:], "updated_at": time.time()}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_version(project_path: Path | str, version_ref: str) -> dict[str, Any]:
    """Package current tree as immutable deploy artifact for version_ref."""
    root = Path(project_path).resolve()
    ref = (version_ref or "").strip() or f"anon-{int(time.time())}"
    from lumen.engine.services.hosting.artifacts import package_project, publish_artifact

    job_key = f"ver_{ref[:16]}"
    zip_path, digest = package_project(root, job_key)
    uri = publish_artifact(zip_path, job_key)
    entry = {
        "version_ref": ref,
        "artifact_uri": uri,
        "sha256": digest,
        "created_at": time.time(),
        "job_key": job_key,
    }
    versions = _load_index(root)
    versions = [v for v in versions if v.get("version_ref") != ref]
    versions.append(entry)
    _save_index(root, versions)
    # Redis index (optional)
    try:
        from lumen.engine.services.hosting.redis_state import _client

        r = _client()
        if r is not None:
            key = f"lumen:host:versions:{digest[:16]}"
            r.setex(key, 86400 * 14, json.dumps(entry, ensure_ascii=False))
    except Exception:
        pass
    return entry


def list_versions(project_path: Path | str) -> list[dict[str, Any]]:
    return list(reversed(_load_index(Path(project_path).resolve())))


def restore_version(project_path: Path | str, version_ref: str) -> dict[str, Any]:
    """Extract a published version over the project directory (destructive)."""
    root = Path(project_path).resolve()
    ref = (version_ref or "").strip()
    versions = _load_index(root)
    match = next((v for v in versions if v.get("version_ref") == ref), None)
    if not match:
        raise FileNotFoundError(f"version_not_found:{ref}")
    from lumen.engine.services.hosting.artifacts import fetch_artifact, extract_artifact

    job_key = str(match.get("job_key") or f"ver_{ref[:16]}")
    zip_path = fetch_artifact(str(match.get("artifact_uri") or ""), job_key)
    work = extract_artifact(zip_path, job_key)
    # Replace project files carefully: copy work → root
    for item in work.iterdir():
        dest = root / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    return {"ok": True, "version_ref": ref, "restored_from": str(work)}


__all__ = ["publish_version", "list_versions", "restore_version"]
