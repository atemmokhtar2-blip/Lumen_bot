"""Single Mongo connection entry — production TLS enforced."""
from __future__ import annotations

import os
from typing import Any


def resolve_mongodb_uri() -> str:
    return (
        (os.getenv("MONGODB_URI") or "")
        or (os.getenv("MONGO_URL") or "")
        or (os.getenv("MONGODB_URL") or "")
        or (os.getenv("MONGO_URI") or "")
    ).strip()


def connect_mongo(uri: str | None = None, **kwargs: Any):
    """MongoClient with production TLS policy."""
    from pymongo import MongoClient

    from lumen.platform.prod_security_gate import enforce_mongo_uri_or_raise

    raw = (uri or resolve_mongodb_uri() or "").strip()
    if not raw:
        raise ValueError("MONGODB_URI is required")
    raw = enforce_mongo_uri_or_raise(raw)
    return MongoClient(raw, **kwargs)


__all__ = ["connect_mongo", "resolve_mongodb_uri"]
