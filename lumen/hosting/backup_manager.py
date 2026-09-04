"""Backup / restore for hosted bots + platform Postgres.

Project backups: SQLite/JSON data under the bot project dir → tar.gz (+ optional S3).
Platform DB: pg_dump when DATABASE_URL is set.

Config:
  TBE_HOST_BACKUP_INTERVAL_HOURS=6
  TBE_HOST_BACKUP_DIR=...
  TBE_HOST_BACKUP_KEEP=10
  TBE_S3_BUCKET=...  (via object_storage)
  TBE_DB_BACKUP_DIR=...  (default under backup root / platform-db)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
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


def _keep_count() -> int:
    try:
        return max(1, int(os.environ.get("TBE_HOST_BACKUP_KEEP") or "10"))
    except ValueError:
        return 10


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
    try:
        found.extend(p for p in project_path.glob("*.sqlite*") if p.is_file())
        found.extend(p for p in project_path.glob("data/**/*.db") if p.is_file())
    except Exception:
        pass
    seen: set[str] = set()
    out: list[Path] = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _prune_old(dest_dir: Path, *, keep: int | None = None) -> int:
    keep_n = keep if keep is not None else _keep_count()
    archives = sorted(dest_dir.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in archives[keep_n:]:
        try:
            old.unlink(missing_ok=True)
            removed += 1
        except Exception:
            pass
    return removed


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

    pruned = _prune_old(dest_dir)

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
        "pruned": pruned,
    }


def list_backups(instance_id: str) -> list[dict[str, Any]]:
    iid = (instance_id or "").replace("/", "_")[:64]
    dest_dir = _backup_root() / iid
    if not dest_dir.is_dir():
        return []
    rows = []
    for p in sorted(dest_dir.glob("*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
        rows.append(
            {
                "path": str(p),
                "name": p.name,
                "bytes": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
        )
    return rows


def restore_project(
    archive_path: Path | str,
    project_path: Path | str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Extract a project backup tar.gz into project_path (overwrite data files only)."""
    arc = Path(archive_path).resolve()
    root = Path(project_path).resolve()
    if not arc.is_file():
        return {"ok": False, "error": "archive_missing"}
    if not root.is_dir():
        return {"ok": False, "error": "project_missing"}
    # Safety: only restore relative paths without ..
    restored: list[str] = []
    try:
        with tarfile.open(arc, "r:gz") as tar:
            for m in tar.getmembers():
                name = (m.name or "").lstrip("./")
                if not name or name.startswith("..") or name.startswith("/"):
                    continue
                if name == "manifest.json":
                    continue
                if not m.isfile():
                    continue
                target = (root / name).resolve()
                if not str(target).startswith(str(root)):
                    continue
                if dry_run:
                    restored.append(name)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(m)
                if src is None:
                    continue
                target.write_bytes(src.read())
                restored.append(name)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "restored": restored}
    return {"ok": True, "restored": restored, "count": len(restored), "dry_run": dry_run}


def backup_platform_database() -> dict[str, Any]:
    """pg_dump of DATABASE_URL into backup root (requires pg_dump on PATH)."""
    dsn = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("TBE_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not dsn:
        return {"ok": False, "error": "no_database_url", "skipped": True}
    if not shutil.which("pg_dump"):
        return {"ok": False, "error": "pg_dump_not_found", "skipped": True}
    dest = _backup_root() / "platform-db"
    dest.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = dest / f"lumen-db-{stamp}.sql.gz"
    try:
        # Stream pg_dump | gzip
        dump = subprocess.Popen(
            ["pg_dump", "--no-owner", "--no-acl", dsn],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert dump.stdout is not None
        import gzip

        with gzip.open(out, "wb") as gz:
            shutil.copyfileobj(dump.stdout, gz)
        _, err = dump.communicate(timeout=600)
        if dump.returncode != 0:
            try:
                out.unlink(missing_ok=True)
            except Exception:
                pass
            return {"ok": False, "error": f"pg_dump:{err.decode(errors='replace')[:300]}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
    _prune_old(dest, keep=_keep_count())
    # also prune .sql.gz by mtime
    archives = sorted(dest.glob("*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in archives[_keep_count():]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass
    return {
        "ok": True,
        "path": str(out),
        "bytes": out.stat().st_size if out.is_file() else 0,
    }


def backup_all_running(hosting_service) -> list[dict[str, Any]]:
    results = []
    for inst in list(getattr(hosting_service, "_instances", {}) or {}).values():
        if (getattr(inst, "status", "") or "") != "running":
            continue
        results.append(
            backup_project(inst.project_path, instance_id=getattr(inst, "instance_id", ""))
        )
    # Platform DB each cycle (best-effort)
    try:
        results.append(backup_platform_database())
    except Exception as exc:
        results.append({"ok": False, "error": type(exc).__name__, "scope": "platform_db"})
    return results


def interval_hours() -> float:
    try:
        return max(1.0, float(os.environ.get("TBE_HOST_BACKUP_INTERVAL_HOURS") or "6"))
    except Exception:
        return 6.0


__all__ = [
    "backup_project",
    "backup_all_running",
    "backup_platform_database",
    "restore_project",
    "list_backups",
    "interval_hours",
]
