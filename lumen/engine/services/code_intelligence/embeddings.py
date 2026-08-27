"""Neural code embeddings — production default is real models, not hash.

Provider resolution (CODE_EMBEDDING_PROVIDER, default=auto):

  1) voyage   — voyage-code-4 via Voyage API (VOYAGE_API_KEY / CODE_EMBEDDING_API_KEY)
  2) openai   — OpenAI-compatible embeddings API
  3) qwen     — Qwen3-Embedding via OpenAI-compatible base URL
  4) fastembed — local neural (fastembed) when installed
  5) hash     — deterministic bag-of-tokens; DEV ONLY

auto cascade:
  key+voyage → voyage
  else try fastembed (real neural offline)
  else hash only if CODE_EMBEDDING_ALLOW_HASH=1 or non-production

Production (ENVIRONMENT=production|prod|staging):
  never silently returns local_hash unless CODE_EMBEDDING_ALLOW_HASH=1.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}")
_FASTEMBED_MODEL = None

# World-class defaults (2026)
_DEFAULT_VOYAGE_MODEL = "voyage-code-4"
_DEFAULT_OPENAI_MODEL = "text-embedding-3-large"
_DEFAULT_QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
# Prefer a code-capable small model when available; MiniLM remains universal fallback
_DEFAULT_FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def tokenize_code(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def embed_text_local(text: str, *, dims: int = 256) -> list[float]:
    """Deterministic hash embedding — offline tests / explicit allow only."""
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


def _api_key() -> str:
    return (
        os.getenv("CODE_EMBEDDING_API_KEY")
        or os.getenv("VOYAGE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()


def resolve_embedding_provider() -> str:
    """Resolve effective provider name for auto / explicit settings."""
    raw = (os.getenv("CODE_EMBEDDING_PROVIDER") or "auto").strip().lower()
    if raw and raw != "auto":
        return raw

    # auto cascade — strongest available neural first
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
        pass
    return "hash"


def _fastembed_model():
    global _FASTEMBED_MODEL
    if _FASTEMBED_MODEL is not None:
        return _FASTEMBED_MODEL
    from fastembed import TextEmbedding

    model_name = (
        os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_FASTEMBED_MODEL
    ).strip()
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


def _embed_external(texts: list[str], *, provider: str, dims: int) -> dict[str, Any]:
    import requests

    key = _api_key()
    if not key:
        raise RuntimeError("embedding_api_key_missing")

    if provider == "voyage":
        url = "https://api.voyageai.com/v1/embeddings"
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_VOYAGE_MODEL).strip()
        payload: dict[str, Any] = {"input": texts, "model": model}
        # Optional output dimension (Matryoshka) for voyage-code-4
        out_dim = (os.getenv("CODE_EMBEDDING_DIMS") or "").strip()
        if out_dim.isdigit():
            payload["output_dimension"] = int(out_dim)
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        vectors = [row["embedding"] for row in data.get("data") or []]
        return {
            "ok": True,
            "provider": "voyage",
            "model": model,
            "vectors": vectors,
            "dims": len(vectors[0]) if vectors else 0,
            "neural": True,
        }

    # openai + qwen share OpenAI-compatible /embeddings
    if provider == "qwen":
        base = (
            os.getenv("CODE_EMBEDDING_BASE_URL")
            or os.getenv("QWEN_EMBEDDING_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_QWEN_MODEL).strip()
    else:
        base = (os.getenv("CODE_EMBEDDING_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model = (os.getenv("CODE_EMBEDDING_MODEL") or _DEFAULT_OPENAI_MODEL).strip()

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
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "vectors": vectors,
        "dims": len(vectors[0]) if vectors else 0,
        "neural": True,
    }


def embed_texts(texts: list[str], *, dims: int = 256) -> dict[str, Any]:
    """Embed texts with neural default cascade. Hash is last-resort / explicit only."""
    texts = [str(t or "") for t in texts]
    provider = resolve_embedding_provider()

    if provider in {"voyage", "openai", "qwen"}:
        try:
            return _embed_external(texts, provider=provider, dims=dims)
        except Exception as exc:
            logger.warning("neural embed %s failed: %s", provider, exc)
            # Fall through to fastembed then hash policy
            err = f"{type(exc).__name__}:{exc}"
        else:
            err = ""
    else:
        err = ""

    if provider in {"fastembed", "auto", "voyage", "openai", "qwen", "hash"}:
        # After API failure or auto without key: try local neural
        if provider != "hash":
            try:
                return embed_fastembed(texts)
            except Exception as exc:
                logger.debug("fastembed unavailable: %s", exc)
                if provider == "fastembed":
                    if not _allow_hash() and _is_production():
                        return {
                            "ok": False,
                            "provider": "fastembed",
                            "error": f"{type(exc).__name__}:{exc}",
                            "vectors": [],
                            "neural": False,
                        }
                    return {
                        "ok": False,
                        "provider": "fastembed",
                        "error": f"{type(exc).__name__}:{exc}",
                        "vectors": embed_batch_local(texts, dims=dims),
                        "fallback": "local_hash",
                        "neural": False,
                    }

    # Hash path — blocked in production unless explicitly allowed
    if _is_production() and not _allow_hash():
        return {
            "ok": False,
            "provider": "local_hash",
            "error": err or "neural_embeddings_required_in_production",
            "vectors": [],
            "dims": dims,
            "neural": False,
        }

    return {
        "ok": True,
        "provider": "local_hash",
        "vectors": embed_batch_local(texts, dims=dims),
        "dims": dims,
        "neural": False,
        "fallback": True,
    }


__all__ = [
    "tokenize_code",
    "embed_text_local",
    "embed_batch_local",
    "embed_texts",
    "embed_fastembed",
    "cosine",
    "resolve_embedding_provider",
]
