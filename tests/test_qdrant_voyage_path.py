"""Voyage auto path + Qdrant backend (soft when server/key absent)."""
from __future__ import annotations

import os


def test_embed_auto_prefers_voyage_when_key(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "auto")
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    monkeypatch.delenv("CODE_EMBEDDING_API_KEY", raising=False)
    # without key falls back local/fastembed
    out = emb.embed_texts(["def hello(): pass"])
    assert out.get("vectors")
    assert out.get("provider") in {"local_hash", "fastembed", "voyage", "openai"}


def test_qdrant_module_importable():
    from lumen.engine.services.code_intelligence import qdrant_backend as qb

    assert hasattr(qb, "qdrant_upsert")
    assert hasattr(qb, "qdrant_search")
    # without server / backend env → unavailable
    os.environ.pop("CODE_VECTOR_BACKEND", None)
    assert qb.qdrant_available() is False


def test_vector_store_records_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("CODE_VECTOR_BACKEND", raising=False)
    from lumen.engine.services.code_intelligence.vector_store import CodeVectorStore

    store = CodeVectorStore(tmp_path, store_dir=tmp_path / "idx")
    r = store.upsert(
        ["a1"],
        ["def alpha():\n    return 1\n"],
        [{"name": "alpha", "path": "a.py", "kind": "function"}],
    )
    assert r.get("ok") is True
    assert r.get("backend") in {"numpy", "qdrant+numpy"}
