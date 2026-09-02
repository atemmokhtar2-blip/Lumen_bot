"""Periodic backup of hosted project data (SQLite/JSON) to local + optional S3.

Config:
  TBE_HOST_BACKUP_INTERVAL_HOURS=6
  TBE_HOST_BACKUP_DIR=...
  TBE_S3_BUCKET=...  (via object_storage)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tarfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.backup")


def _backup_root() -> Path:
    raw = (os.environ.get("TBE_HOST_BACKUP_DIR") or "").strip()
    if raw:
        p = Path(raw)
    else:
        try:
            from lumen.bot.config import OUTPUT_DIR

            p = Path(OUTPUT_DIR) / "hosting" / "backups"
        except Exception:
            p = Path.home() / ".lumen" / "hosting" / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _data_candidates(project_path: Path) -> list[Path]:
    names = (
        "bot.db",
        "data.db",
        "app.db",
        "database.sqlite",
        "database.sqlite3",
        "storage.json",
        "data.json",
        ".lumen_secrets.sealed",
        ".lumen_host_versions.json",
    )
    found: list[Path] = []
    for n in names:
        p = project_path / n
        if p.is_file():
            found.append(p)
    # any *.sqlite*
    try:
        found.extend(p for p in project_path.glob("*.sqlite*") if p.is_file())
        found.extend(p for p in project_path.glob("data/**/*.db") if p.is_file())
    except Exception:
        pass
    # dedupe
    seen = set()
    out = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def backup_project(project_path: Path | str, *, instance_id: str = "") -> dict[str, Any]:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return {"ok": False, "error": "project_missing"}
    files = _data_candidates(root)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    iid = (instance_id or root.name).replace("/", "_")[:64]
    dest_dir = _backup_root() / iid
    dest_dir.mkdir(parents=True, exist_ok=True)
    tar_path = dest_dir / f"{iid}-{stamp}.tar.gz"
    try:
        with tarfile.open(tar_path, "w:gz") as tar:
            for f in files:
                try:
                    tar.add(f, arcname=f.relative_to(root).as_posix())
                except Exception:
                    pass
            # always include a manifest
            manifest = dest_dir / f"manifest-{stamp}.json"
            meta = {
                "instance_id": iid,
                "project_path": str(root),
                "files": [f.relative_to(root).as_posix() for f in files],
                "created_at": time.time(),
            }
            manifest.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            tar.add(manifest, arcname="manifest.json")
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

    s3_uri = None
    try:
        from lumen.engine.services.object_storage import enabled, upload_file

        if enabled():
            key = f"host-backups/{iid}/{tar_path.name}"
            s3_uri = upload_file(tar_path, key)
    except Exception as exc:
        logger.warning("backup s3 upload failed: %s", type(exc).__name__)

    return {
        "ok": True,
        "path": str(tar_path),
        "s3": s3_uri,
        "file_count": len(files),
        "bytes": tar_path.stat().st_size if tar_path.is_file() else 0,
    }


def backup_all_running(hosting_service) -> list[dict[str, Any]]:
    results = []
    for inst in list(getattr(hosting_service, "_instances", {}) or {}).values():
        if (getattr(inst, "status", "") or "") != "running":
            continue
        results.append(
            backup_project(inst.project_path, instance_id=getattr(inst, "instance_id", ""))
        )
    return results


def interval_hours() -> float:
    try:
        return max(1.0, float(os.environ.get("TBE_HOST_BACKUP_INTERVAL_HOURS") or "6"))
    except Exception:
        return 6.0


__all__ = ["backup_project", "backup_all_running", "interval_hours"]
