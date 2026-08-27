"""Phase 2.A — neural embeddings hardened (input_type, batch, strict)."""
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


def test_voyage_model_default_is_code_4():
    import lumen.engine.services.code_intelligence.embeddings as emb

    assert emb._DEFAULT_VOYAGE_MODEL == "voyage-code-4"


def test_embed_query_sets_input_type_voyage(monkeypatch):
    """Mock Voyage HTTP and assert input_type=query is sent."""
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "vk-test")
    captured = {}

    def fake_post(url, headers=None, payload=None):
        captured["url"] = url
        captured["payload"] = payload
        n = len(payload.get("input") or [])
        return {
            "data": [
                {"index": i, "embedding": [0.1 * (i + 1), 0.2, 0.3, 0.4]}
                for i in range(n)
            ]
        }

    monkeypatch.setattr(emb, "_http_post_json", lambda url, headers, payload: fake_post(url, headers, payload))
    out = emb.embed_query("find login_user")
    assert out.get("ok") is True
    assert out.get("neural") is True
    assert captured["payload"].get("input_type") == "query"
    assert captured["payload"].get("model") == "voyage-code-4"
    assert len(out.get("vector") or []) == 4


def test_embed_documents_sets_input_type_document(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "vk-test")
    captured = {}

    def fake_post(url, headers=None, payload=None):
        captured["payload"] = payload
        n = len(payload.get("input") or [])
        return {
            "data": [{"index": i, "embedding": [float(i), 1.0, 0.0]} for i in range(n)]
        }

    monkeypatch.setattr(emb, "_http_post_json", lambda url, headers, payload: fake_post(url, headers, payload))
    out = emb.embed_documents(["def a(): pass", "def b(): pass"])
    assert out.get("ok") is True
    assert captured["payload"].get("input_type") == "document"
    assert len(out.get("vectors") or []) == 2


def test_voyage_batches_large_input(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "vk-test")
    monkeypatch.setattr(emb, "_VOYAGE_BATCH", 3)
    calls = []

    def fake_post(url, headers=None, payload=None):
        calls.append(len(payload.get("input") or []))
        n = len(payload.get("input") or [])
        return {
            "data": [{"index": i, "embedding": [1.0, 0.0]} for i in range(n)]
        }

    monkeypatch.setattr(emb, "_http_post_json", lambda url, headers, payload: fake_post(url, headers, payload))
    texts = [f"doc {i}" for i in range(7)]
    out = emb.embed_documents(texts)
    assert out.get("ok") is True
    assert len(out["vectors"]) == 7
    assert calls == [3, 3, 1]


def test_strict_no_hash_after_api_failure(monkeypatch):
    from lumen.engine.services.code_intelligence import embeddings as emb

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CODE_EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "vk-bad")
    monkeypatch.delenv("CODE_EMBEDDING_ALLOW_HASH", raising=False)

    def boom(*a, **k):
        raise RuntimeError("api_down")

    monkeypatch.setattr(emb, "_http_post_json", boom)

    # Also make fastembed fail
    def no_fe(texts):
        raise RuntimeError("no_fastembed")

    monkeypatch.setattr(emb, "embed_fastembed", no_fe)
    out = emb.embed_texts(["x"])
    assert out.get("ok") is False
    assert out.get("vectors") == []
