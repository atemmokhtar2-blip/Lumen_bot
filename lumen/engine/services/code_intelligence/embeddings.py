"""Neural code embeddings — production-grade default (2026).

Cascade (CODE_EMBEDDING_PROVIDER=auto):
  1) voyage-code-4  (VOYAGE_API_KEY) — code retrieval specialist
  2) openai / qwen  (OpenAI-compatible /embeddings)
  3) fastembed      (local neural)
  4) hash           (dev only; blocked in production unless ALLOW_HASH)

Voyage retrieval quality requires input_type=query|document (official docs).
Large batches are chunked; transient HTTP errors are retried.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time
from typing import Any, Literal

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}")
_FASTEMBED_MODEL = None

_DEFAULT_VOYAGE_MODEL = "voyage-code-4"
_DEFAULT_OPENAI_MODEL = "text-embedding-3-large"
_DEFAULT_QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_DEFAULT_FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Semantic-memory embedding model — multilingual (50+ languages incl. Arabic).
# Same 384-dim as the English code default so it is a drop-in for the memory
# store, but trained on multilingual parallel corpora. This is the strongest
# fastembed-supported model for Arabic retrieval (Mr. TyDi MRR@10 ~71.5 for
# the multilingual-e5 family vs BM25 ~36.7). Kept separate from
# CODE_EMBEDDING_MODEL so code embeddings (English code-specialist) and
# semantic memory (multilingual natural language) use the right model each.
_DEFAULT_SEMANTIC_FASTEMBED_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# Voyage constraints (docs): max 1000 strings per request
_VOYAGE_BATCH = 64
_HTTP_RETRIES = 3
_HTTP_BACKOFF_S = 0.6

InputType = Literal["query", "document"] | None


def tokenize_code(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def embed_text_local(text: str, *, dims: int = 256) -> list[float]:
    """Deterministic hash embedding — tests / explicit allow only."""
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


def _is_production() -> bool:
    return (os.getenv("ENVIRONMENT") or "").strip().lower() in {
        "production",
        "prod",
        "staging",
    }


def _allow_hash() -> bool:
    return (os.getenv("CODE_EMBEDDING_ALLOW_HASH") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _strict_neural() -> bool:
    """When true, never return hash vectors after neural failure."""
    if _allow_hash():
        return False
    if (os.getenv("CODE_EMBEDDING_STRICT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    return _is_production()


def _api_key() -> str:
    return (
        os.getenv("CODE_EMBEDDING_API_KEY")
        or os.getenv("VOYAGE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()


def resolve_embedding_provider() -> str:
    raw = (os.getenv("CODE_EMBEDDING_PROVIDER") or "auto").strip().lower()
    if raw and raw != "auto":
        return raw
    if (os.getenv("VOYAGE_API_KEY") or "").strip():
        return "voyage"
    base = (os.getenv("CODE_EMBEDDING_BASE_URL") or "").strip().lower()
    if (os.getenv("CODE_EMBEDDING_API_KEY") or "").strip():
        if "qwen" in base:
            return "qwen"
        if "voyage" in base:
            return "voyage"
        return "openai"
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        return "openai"
    try:
        import fastembed  # noqa: F401

        return "fastembed"
    except Exception:
        return "hash"


def _fastembed_model():
    global _FASTEMBED_MODEL
    if _FASTEMBED_MODEL is not None:
        return _FASTEMBED_MODEL
    from fastembed import TextEmbedding

    model_name = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_FASTEMBED_MODEL).strip()
    _FASTEMBED_MODEL = TextEmbedding(model_name=model_name)
    return _FASTEMBED_MODEL


def embed_fastembed(texts: list[str]) -> dict[str, Any]:
    model = _fastembed_model()
    vectors = [list(map(float, v)) for v in model.embed(texts)]
    model_name = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_FASTEMBED_MODEL).strip()
    return {
        "ok": True,
        "provider": "fastembed",
        "model": model_name,
        "vectors": vectors,
        "dims": len(vectors[0]) if vectors else 0,
        "neural": True,
    }


# ---- semantic-memory embeddings (multilingual, Arabic-capable) ----
_SEM_FASTEMBED_MODEL = None


def _semantic_fastembed_model():
    """Lazy-load the multilingual fastembed model (separate cache from code)."""
    global _SEM_FASTEMBED_MODEL
    if _SEM_FASTEMBED_MODEL is not None:
        return _SEM_FASTEMBED_MODEL
    from fastembed import TextEmbedding

    model_name = (
        os.getenv("SEMANTIC_EMBEDDING_MODEL") or _DEFAULT_SEMANTIC_FASTEMBED_MODEL
    ).strip()
    _SEM_FASTEMBED_MODEL = TextEmbedding(model_name=model_name)
    return _SEM_FASTEMBED_MODEL


def embed_query_semantic(text: str) -> dict[str, Any]:
    """Embed a single natural-language query with the multilingual model.

    Used by the semantic-memory store for recall. Falls back to the standard
    neural cascade if the multilingual model is unavailable, then to empty.
    """
    text = str(text or "")
    if not text.strip():
        return {"ok": True, "provider": "empty", "vector": [], "dims": 0, "neural": True}
    try:
        model = _semantic_fastembed_model()
        vecs = list(model.embed([text]))
        if vecs:
            v = [float(x) for x in vecs[0]]
            return {
                "ok": True,
                "provider": "fastembed-semantic",
                "model": (os.getenv("SEMANTIC_EMBEDDING_MODEL") or _DEFAULT_SEMANTIC_FASTEMBED_MODEL).strip(),
                "vector": v,
                "dims": len(v),
                "neural": True,
            }
    except Exception as exc:
        logger.debug("semantic multilingual embed_query failed: %s", exc)
    # graceful fallback to the standard cascade (still neural, English-centric)
    return embed_query(text)


def embed_documents_semantic(texts: list[str]) -> dict[str, Any]:
    """Embed a batch of natural-language documents with the multilingual model."""
    texts = [str(t or "") for t in texts]
    if not texts:
        return {"ok": True, "provider": "empty", "vectors": [], "dims": 0, "neural": True}
    try:
        model = _semantic_fastembed_model()
        vecs = [[float(x) for x in v] for v in model.embed(texts)]
        if len(vecs) == len(texts):
            return {
                "ok": True,
                "provider": "fastembed-semantic",
                "model": (os.getenv("SEMANTIC_EMBEDDING_MODEL") or _DEFAULT_SEMANTIC_FASTEMBED_MODEL).strip(),
                "vectors": vecs,
                "dims": len(vecs[0]) if vecs else 0,
                "neural": True,
            }
    except Exception as exc:
        logger.debug("semantic multilingual embed_batch failed: %s", exc)
    return embed_documents(texts)


def _chunk(texts: list[str], size: int) -> list[list[str]]:
    size = max(1, int(size))
    return [texts[i : i + size] for i in range(0, len(texts), size)]


def _http_post_json(url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    import requests

    last_exc: Exception | None = None
    for attempt in range(_HTTP_RETRIES):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            if resp.status_code in {429, 500, 502, 503, 504} and attempt + 1 < _HTTP_RETRIES:
                time.sleep(_HTTP_BACKOFF_S * (2**attempt))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < _HTTP_RETRIES:
                time.sleep(_HTTP_BACKOFF_S * (2**attempt))
                continue
            raise
    raise RuntimeError(f"embed_http_failed:{last_exc}")


def _voyage_embed_batch(
    texts: list[str],
    *,
    model: str,
    key: str,
    input_type: InputType,
) -> list[list[float]]:
    payload: dict[str, Any] = {
        "input": texts,
        "model": model,
        "truncation": True,
    }
    if input_type in {"query", "document"}:
        payload["input_type"] = input_type
    out_dim = (os.getenv("CODE_EMBEDDING_DIMS") or "").strip()
    if out_dim.isdigit() and int(out_dim) in {256, 512, 1024, 2048}:
        payload["output_dimension"] = int(out_dim)
    data = _http_post_json(
        "https://api.voyageai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload=payload,
    )
    rows = sorted(data.get("data") or [], key=lambda r: int(r.get("index") or 0))
    return [list(map(float, row["embedding"])) for row in rows]


def _openai_compatible_embed_batch(
    texts: list[str],
    *,
    base: str,
    model: str,
    key: str,
) -> list[list[float]]:
    data = _http_post_json(
        f"{base.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload={"input": texts, "model": model},
    )
    rows = sorted(data.get("data") or [], key=lambda r: int(r.get("index") or 0))
    return [list(map(float, row["embedding"])) for row in rows]


def _embed_external(
    texts: list[str],
    *,
    provider: str,
    input_type: InputType = None,
) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise RuntimeError("embedding_api_key_missing")

    if provider == "voyage":
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_VOYAGE_MODEL).strip()
        vectors: list[list[float]] = []
        for part in _chunk(texts, _VOYAGE_BATCH):
            vectors.extend(
                _voyage_embed_batch(part, model=model, key=key, input_type=input_type)
            )
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"voyage_vector_count_mismatch:{len(vectors)}!={len(texts)}"
            )
        return {
            "ok": True,
            "provider": "voyage",
            "model": model,
            "vectors": vectors,
            "dims": len(vectors[0]) if vectors else 0,
            "neural": True,
            "input_type": input_type,
        }

    if provider == "qwen":
        base = (
            os.getenv("CODE_EMBEDDING_BASE_URL")
            or os.getenv("QWEN_EMBEDDING_BASE_URL")
            or "https://api.openai.com/v1"
        )
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_QWEN_MODEL).strip()
    else:
        base = os.getenv("CODE_EMBEDDING_BASE_URL") or "https://api.openai.com/v1"
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_OPENAI_MODEL).strip()

    vectors = []
    for part in _chunk(texts, _VOYAGE_BATCH):
        vectors.extend(
            _openai_compatible_embed_batch(part, base=base, model=model, key=key)
        )
    if len(vectors) != len(texts):
        raise RuntimeError(f"embed_vector_count_mismatch:{len(vectors)}!={len(texts)}")
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "vectors": vectors,
        "dims": len(vectors[0]) if vectors else 0,
        "neural": True,
        "input_type": input_type,
    }


def _fail(provider: str, error: str, *, dims: int = 256) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": provider,
        "error": error,
        "vectors": [],
        "dims": dims,
        "neural": False,
    }


def embed_texts(
    texts: list[str],
    *,
    dims: int = 256,
    input_type: InputType = None,
) -> dict[str, Any]:
    """Embed texts with neural-first cascade.

    For retrieval, call embed_query / embed_documents so Voyage gets input_type.
    """
    texts = [str(t or "") for t in texts]
    if not texts:
        return {
            "ok": True,
            "provider": "empty",
            "vectors": [],
            "dims": 0,
            "neural": True,
        }

    provider = resolve_embedding_provider()
    err = ""

    if provider in {"voyage", "openai", "qwen"}:
        try:
            return _embed_external(texts, provider=provider, input_type=input_type)
        except Exception as exc:
            err = f"{type(exc).__name__}:{exc}"
            logger.warning("neural embed %s failed: %s", provider, exc)

    if provider != "hash":
        try:
            return embed_fastembed(texts)
        except Exception as exc:
            logger.debug("fastembed unavailable: %s", exc)
            if provider == "fastembed" and _strict_neural():
                return _fail("fastembed", f"{type(exc).__name__}:{exc}", dims=dims)
            err = err or f"fastembed:{type(exc).__name__}:{exc}"

    if _strict_neural():
        return _fail(
            provider or "local_hash",
            err or "neural_embeddings_required",
            dims=dims,
        )

    return {
        "ok": True,
        "provider": "local_hash",
        "vectors": embed_batch_local(texts, dims=dims),
        "dims": dims,
        "neural": False,
        "fallback": True,
    }


def embed_query(text: str, *, dims: int = 256) -> dict[str, Any]:
    """Embed a search query (Voyage input_type=query)."""
    out = embed_texts([text], dims=dims, input_type="query")
    if out.get("ok") and out.get("vectors"):
        return {
            **out,
            "vector": out["vectors"][0],
        }
    return {**out, "vector": []}


def embed_documents(texts: list[str], *, dims: int = 256) -> dict[str, Any]:
    """Embed corpus documents (Voyage input_type=document)."""
    return embed_texts(texts, dims=dims, input_type="document")


__all__ = [
    "tokenize_code",
    "embed_text_local",
    "embed_batch_local",
    "embed_texts",
    "embed_query",
    "embed_documents",
    "embed_query_semantic",
    "embed_documents_semantic",
    "embed_fastembed",
    "cosine",
    "resolve_embedding_provider",
]
