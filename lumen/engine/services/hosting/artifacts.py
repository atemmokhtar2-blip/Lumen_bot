"""Portable build artifacts — the missing link for multi-node workers.

Problem: project_path on the API host is invisible to other worker nodes.
Solution: at enqueue time, package a clean source tarball/zip into an artifact
store. Workers download the artifact, build the image, push, and run.

Backends (first match wins):
  1) S3/R2 when TBE_S3_BUCKET set (object_storage)
  2) Shared filesystem TBE_ARTIFACT_ROOT (NFS/EFS) — readable by all workers
  3) Local OUTPUT_DIR/artifacts (single-node only; workers on same disk)
"""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import hashlib
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tbe.hosting.artifacts")

_SKIP_NAMES = {
    ".tbe_bot_token", ".env", ".env.local", ".env.production", "secrets.json",
    ".tbe_smoke_runner.py", ".git",
}
_SKIP_PARTS = {".git", "__pycache__", ".venv", "venv", ".mypy_cache", ".ruff_cache"}


def artifact_root() -> Path:
    raw = (os.environ.get("TBE_ARTIFACT_ROOT") or "").strip()
    if raw:
        p = Path(raw).resolve()
    else:
        p = Path(os.environ.get("OUTPUT_DIR") or _cm_default_output_dir()).resolve() / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in _SKIP_PARTS for part in rel.parts):
        return True
    if path.name in _SKIP_NAMES:
        return True
    low = path.name.lower()
    if "secret" in low or (path.suffix in {".pem", ".key"} and "token" in low):
        return True
    if path.suffix in {".pyc", ".pyo", ".log", ".zip"}:
        return True
    return False


def package_project(project_path: Path, job_id: str) -> tuple[Path, str]:
    """Zip clean sources. Returns (local_zip_path, sha256_hex)."""
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project_missing:{root}")
    dest = artifact_root() / f"{job_id}.zip"
    from lumen.engine.services.safe_zip import write_project_zip

    out = write_project_zip(root, dest)
    if out is None or not out.is_file():
        raise RuntimeError(f"artifact_zip_failed:{root}")
    # Hash archive for integrity sidecar
    h = hashlib.sha256()
    h.update(out.read_bytes())
    digest = h.hexdigest()
    (artifact_root() / f"{job_id}.sha256").write_text(digest + "\n", encoding="utf-8")
    return out, digest


def publish_artifact(local_zip: Path, job_id: str) -> str:
    """Publish to S3 if configured; always keep local/shared copy.

    Returns artifact URI: s3://... or file://...
    """
    try:
        from lumen.engine.services.object_storage import enabled, upload_file
        if enabled():
            key = f"artifacts/{job_id}.zip"
            uri = upload_file(local_zip, key)
            if uri:
                return uri
    except Exception:
        logger.exception("s3 artifact upload failed; using filesystem URI")
    return f"file://{local_zip.resolve()}"


def fetch_artifact(artifact_uri: str, job_id: str) -> Path:
    """Materialize artifact zip on this node; return local zip path."""
    uri = (artifact_uri or "").strip()
    dest = artifact_root() / f"{job_id}.zip"

    if uri.startswith("s3://") or (not uri.startswith("file://") and "://" not in uri and enabled_s3()):
        # object key form
        key = uri
        if uri.startswith("s3://"):
            # s3://bucket/key
            parts = uri[5:].split("/", 1)
            key = parts[1] if len(parts) == 2 else f"artifacts/{job_id}.zip"
        else:
            key = uri
        from lumen.engine.services.object_storage import download_file
        if not download_file(key if not key.startswith("artifacts/") else key, dest):
            # try standard key
            if not download_file(f"artifacts/{job_id}.zip", dest):
                raise FileNotFoundError(f"artifact_download_failed:{uri}")
        return dest

    if uri.startswith("file://"):
        src = Path(uri[7:])
        if not src.is_file():
            # shared root fallback by job id
            alt = artifact_root() / f"{job_id}.zip"
            if alt.is_file():
                return alt
            raise FileNotFoundError(f"artifact_file_missing:{src}")
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest

    # bare path
    src = Path(uri)
    if src.is_file():
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest

    alt = artifact_root() / f"{job_id}.zip"
    if alt.is_file():
        return alt
    raise FileNotFoundError(f"artifact_not_found:{uri}")


def enabled_s3() -> bool:
    try:
        from lumen.engine.services.object_storage import enabled
        return enabled()
    except Exception:
        return False


def extract_artifact(zip_path: Path, job_id: str) -> Path:
    """Extract to a clean workdir for docker build."""
    work = artifact_root() / "work" / job_id
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # prevent zip-slip
        root = work.resolve()
        for info in zf.infolist():
            target = (work / info.filename).resolve()
            if not str(target).startswith(str(root)):
                raise RuntimeError("zip_slip_rejected")
        zf.extractall(work)
    return work


def cleanup_work(job_id: str) -> None:
    work = artifact_root() / "work" / job_id
    shutil.rmtree(work, ignore_errors=True)
