"""Production vector backend — official qdrant-client.

Env:
  CODE_VECTOR_BACKEND=qdrant
  QDRANT_URL=http://localhost:6333
  QDRANT_API_KEY=   (optional)
  QDRANT_COLLECTION=lumen_code
"""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any


def _collection() -> str:
    return (os.getenv("QDRANT_COLLECTION") or "lumen_code").strip() or "lumen_code"


def _client():
    from qdrant_client import QdrantClient

    url = (os.getenv("QDRANT_URL") or "http://localhost:6333").strip()
    key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
    return QdrantClient(url=url, api_key=key, timeout=30)


def _ensure_collection(client, dims: int) -> None:
    from qdrant_client.http import models as qm

    name = _collection()
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=dims, distance=qm.Distance.COSINE),
        )


def qdrant_upsert(
    ids: list[str],
    vectors: list[list[float]],
    metas: list[dict[str, Any]],
) -> dict[str, Any]:
    if not ids or not vectors:
        return {"ok": False, "error": "empty"}
    dims = len(vectors[0])
    client = _client()
    _ensure_collection(client, dims)
    from qdrant_client.http import models as qm

    points = []
    for i, _id in enumerate(ids):
        pid = uuid.UUID(hashlib.md5(_id.encode()).hexdigest())
        points.append(
            qm.PointStruct(
                id=str(pid),
                vector=list(map(float, vectors[i])),
                payload={"chunk_id": _id, **(metas[i] if i < len(metas) else {})},
            )
        )
    client.upsert(collection_name=_collection(), points=points)
    return {
        "ok": True,
        "backend": "qdrant",
        "collection": _collection(),
        "count": len(points),
        "dims": dims,
    }


def qdrant_search(vector: list[float], *, top_k: int = 10) -> list[dict[str, Any]]:
    client = _client()
    name = _collection()
    try:
        hits = client.search(
            collection_name=name,
            query_vector=list(map(float, vector)),
            limit=max(1, min(top_k, 50)),
        )
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}:{exc}"}]
    out = []
    for h in hits:
        payload = dict(h.payload or {})
        out.append(
            {
                "id": payload.get("chunk_id") or str(h.id),
                "score": float(h.score or 0.0),
                "name": payload.get("name"),
                "path": payload.get("path"),
                "kind": payload.get("kind"),
                "start_line": payload.get("start_line"),
                "lang": payload.get("lang"),
            }
        )
    return out


def qdrant_available() -> bool:
    if (os.getenv("CODE_VECTOR_BACKEND") or "").strip().lower() not in {"qdrant", "qdrant-client"}:
        return False
    try:
        client = _client()
        client.get_collections()
        return True
    except Exception:
        return False


__all__ = ["qdrant_upsert", "qdrant_search", "qdrant_available"]
