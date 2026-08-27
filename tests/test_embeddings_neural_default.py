"""Phase 2.A — neural embeddings as production default."""
from __future__ import annotations


def test_resolve_voyage_when_key(monkeypatch):
    from lumen.engine.services.code_intelligence.embeddings import resolve_embedding_provider

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "auto")
    monkeypatch.setenv("VOYAGE_API_KEY", "vk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_embedding_provider() == "voyage"


def test_resolve_openai_when_only_openai_key(monkeypatch):
    from lumen.engine.services.code_intelligence.embeddings import resolve_embedding_provider

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "auto")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("CODE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_embedding_provider() == "openai"


def test_resolve_explicit_provider(monkeypatch):
    from lumen.engine.services.code_intelligence.embeddings import resolve_embedding_provider

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "qwen")
    assert resolve_embedding_provider() == "qwen"


def test_production_blocks_silent_hash(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("CODE_EMBEDDING_ALLOW_HASH", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("CODE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # force hash provider path without fastembed success by provider=hash
    out = emb.embed_texts(["def x(): pass"])
    assert out.get("ok") is False
    assert out.get("vectors") == []
    assert out.get("neural") is False


def test_dev_hash_allowed_without_keys(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("CODE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = emb.embed_texts(["def hello_world():\n    return 1\n"])
    assert out.get("ok") is True
    assert out.get("provider") == "local_hash"
    assert len(out.get("vectors") or []) == 1
    assert len(out["vectors"][0]) == 256


def test_cosine_and_local_batch():
    from lumen.engine.services.code_intelligence.embeddings import (
        cosine,
        embed_batch_local,
        embed_text_local,
    )

    a = embed_text_local("login_user password auth")
    b = embed_text_local("login_user password auth")
    c = embed_text_local("unrelated_billing_refund")
    assert cosine(a, b) > 0.99
    assert cosine(a, c) < cosine(a, b)
    batch = embed_batch_local(["a", "b"])
    assert len(batch) == 2


def test_voyage_model_default_is_code_4(monkeypatch):
    import lumen.engine.services.code_intelligence.embeddings as emb

    assert emb._DEFAULT_VOYAGE_MODEL == "voyage-code-4"
