"""Optional object storage for generated project archives (S3-compatible).

When TBE_S3_BUCKET is unset, operations no-op / use local filesystem only.
Compatible with AWS S3, Cloudflare R2, MinIO via endpoint_url.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tbe.object_storage")


def enabled() -> bool:
    return bool((os.getenv("TBE_S3_BUCKET") or "").strip())


def _client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 required for object storage — pip install boto3") from exc
    kwargs = {
        "aws_access_key_id": (os.getenv("TBE_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip() or None,
        "aws_secret_access_key": (os.getenv("TBE_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip() or None,
        "region_name": (os.getenv("TBE_S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or "auto").strip(),
    }
    endpoint = (os.getenv("TBE_S3_ENDPOINT") or "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **{k: v for k, v in kwargs.items() if v is not None})


def upload_file(local_path: str | Path, key: str) -> Optional[str]:
    """Upload a file; return s3://bucket/key or None if disabled/failed."""
    if not enabled():
        return None
    path = Path(local_path)
    if not path.is_file():
        return None
    bucket = (os.getenv("TBE_S3_BUCKET") or "").strip()
    try:
        _client().upload_file(str(path), bucket, key)
        return f"s3://{bucket}/{key}"
    except Exception as e:
        logger.exception("s3 upload failed: %s", e)
        return None


def download_file(key: str, dest: str | Path) -> bool:
    if not enabled():
        return False
    bucket = (os.getenv("TBE_S3_BUCKET") or "").strip()
    dest_p = Path(dest)
    dest_p.parent.mkdir(parents=True, exist_ok=True)
    try:
        _client().download_file(bucket, key, str(dest_p))
        return dest_p.is_file()
    except Exception as e:
        logger.exception("s3 download failed: %s", e)
        return False


def project_archive_key(user_id: int, project_name: str) -> str:
    prefix = (os.getenv("TBE_S3_PREFIX") or "projects").strip().strip("/")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in project_name)[:80]
    return f"{prefix}/u{int(user_id)}/{safe}.zip"
