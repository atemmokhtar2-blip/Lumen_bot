"""Phase C — code embeddings with real providers when available.

Order:
  1) CODE_EMBEDDING_PROVIDER=voyage|openai + API key → HTTP API
  2) CODE_EMBEDDING_PROVIDER=fastembed or auto → fastembed local model (real neural embeddings)
  3) local_hash fallback (deterministic, offline)
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}")
_FASTEMBED_MODEL = None


def tokenize_code(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def embed_text_local(text: str, *, dims: int = 256) -> list[float]:
    vec = [0.0] * dims
    toks = tokenize_code(text)
    if not toks:
        return vec
    for t in toks:
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        idx = h % dims
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_batch_local(texts: list[str], *, dims: int = 256) -> list[list[float]]:
    return [embed_text_local(t, dims=dims) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return float(sum(a[i] * b[i] for i in range(n)))


def _fastembed_model():
    global _FASTEMBED_MODEL
    if _FASTEMBED_MODEL is not None:
        return _FASTEMBED_MODEL
    from fastembed import TextEmbedding

    model_name = (
        os.getenv("CODE_EMBEDDING_MODEL")
        or "sentence-transformers/all-MiniLM-L6-v2"
    ).strip()
    _FASTEMBED_MODEL = TextEmbedding(model_name=model_name)
    return _FASTEMBED_MODEL


def embed_fastembed(texts: list[str]) -> dict[str, Any]:
    model = _fastembed_model()
    vectors = [list(map(float, v)) for v in model.embed(texts)]
    return {
        "ok": True,
        "provider": "fastembed",
        "model": os.getenv("CODE_EMBEDDING_MODEL") or "sentence-transformers/all-MiniLM-L6-v2",
        "vectors": vectors,
        "dims": len(vectors[0]) if vectors else 0,
    }


def embed_texts(texts: list[str], *, dims: int = 256) -> dict[str, Any]:
    provider = (os.getenv("CODE_EMBEDDING_PROVIDER") or "auto").strip().lower()
    # auto: prefer Voyage when key present (production global path)
    if provider == "auto" and (os.getenv("VOYAGE_API_KEY") or os.getenv("CODE_EMBEDDING_API_KEY") or "").strip():
        provider = "voyage"
    if provider in {"voyage", "openai", "qwen"} and (
        os.getenv("CODE_EMBEDDING_API_KEY") or os.getenv("VOYAGE_API_KEY") or ""
    ).strip():
        try:
            return _embed_external(texts, provider=provider, dims=dims)
        except Exception as exc:
            return {
                "ok": False,
                "provider": provider,
                "error": f"{type(exc).__name__}:{exc}",
                "vectors": embed_batch_local(texts, dims=dims),
                "fallback": "local",
            }
    if provider in {"fastembed", "auto"}:
        try:
            import fastembed  # noqa: F401
            return embed_fastembed(texts)
        except Exception as exc:
            if provider == "fastembed":
                return {
                    "ok": False,
                    "provider": "fastembed",
                    "error": f"{type(exc).__name__}:{exc}",
                    "vectors": embed_batch_local(texts, dims=dims),
                    "fallback": "local",
                }
    return {
        "ok": True,
        "provider": "local_hash",
        "vectors": embed_batch_local(texts, dims=dims),
        "dims": dims,
    }


def _embed_external(texts: list[str], *, provider: str, dims: int) -> dict[str, Any]:
    import requests

    key = (os.getenv("CODE_EMBEDDING_API_KEY") or os.getenv("VOYAGE_API_KEY") or "").strip()
    if provider == "voyage":
        url = "https://api.voyageai.com/v1/embeddings"
        model = (os.getenv("CODE_EMBEDDING_MODEL") or "voyage-code-3").strip()
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"input": texts, "model": model},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        vectors = [row["embedding"] for row in data.get("data") or []]
        return {"ok": True, "provider": "voyage", "model": model, "vectors": vectors}
    base = (os.getenv("CODE_EMBEDDING_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = (os.getenv("CODE_EMBEDDING_MODEL") or "text-embedding-3-small").strip()
    resp = requests.post(
        f"{base}/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"input": texts, "model": model},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    vectors = [
        row["embedding"]
        for row in sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
    ]
    return {"ok": True, "provider": provider, "model": model, "vectors": vectors}


__all__ = [
    "tokenize_code",
    "embed_text_local",
    "embed_batch_local",
    "embed_texts",
    "embed_fastembed",
    "cosine",
]
