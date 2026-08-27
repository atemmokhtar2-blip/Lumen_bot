"""Phase 2.C — Hybrid retrieval: BM25 + dense + graph RRF + rerank."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
from lumen.engine.services.code_intelligence.symbol_graph import build_symbol_graph


def _mini_repo(tmp: Path) -> Path:
    (tmp / "auth.py").write_text(
        '''
def login_user(username, password):
    """Authenticate a user session."""
    return True

def logout_user(session_id):
    return False
''',
        encoding="utf-8",
    )
    (tmp / "billing.py").write_text(
        '''
def charge_card(amount):
    return amount

def refund_payment(tx_id):
    return True
''',
        encoding="utf-8",
    )
    (tmp / "main.py").write_text(
        '''
from auth import login_user

def run():
    login_user("a", "b")
''',
        encoding="utf-8",
    )
    return tmp


def test_hybrid_finds_exact_identifier():
    with tempfile.TemporaryDirectory() as td:
        root = _mini_repo(Path(td))
        out = hybrid_search(root, "login_user", top_k=5, rerank=True)
        assert out.get("ok") is True
        assert out.get("engine") == "hybrid-bm25-dense-graph-rrf-rerank"
        names = [str(h.get("name") or "") for h in out.get("hits") or []]
        assert any("login_user" in n for n in names), names
        assert out.get("channels", {}).get("bm25") is True
        assert out.get("channels", {}).get("dense") is True
        assert out.get("channels", {}).get("graph") is True


def test_hybrid_semanticish_query_returns_hits():
    with tempfile.TemporaryDirectory() as td:
        root = _mini_repo(Path(td))
        out = hybrid_search(root, "authenticate user session password", top_k=5)
        assert out.get("ok") is True
        assert len(out.get("hits") or []) >= 1
        # Prefer auth-related over pure billing for this query
        top_paths = [str(h.get("path") or "") for h in (out.get("hits") or [])[:3]]
        assert any("auth" in p for p in top_paths) or any(
            "login" in str(h.get("name") or "") for h in out.get("hits") or []
        ), (top_paths, out.get("hits"))


def test_hybrid_rrf_engine_metadata():
    with tempfile.TemporaryDirectory() as td:
        root = _mini_repo(Path(td))
        out = hybrid_search(root, "charge_card", top_k=3, candidate_pool=20)
        assert out["ok"]
        assert out.get("rrf_k") == 60
        assert out.get("reranker") in {"local_structural", "voyage:rerank-2", "none"} or str(
            out.get("reranker") or ""
        ).startswith("voyage")
        hit = (out.get("hits") or [None])[0]
        assert hit is not None
        assert "path" in hit and "score" in hit


def test_empty_repo_ok():
    with tempfile.TemporaryDirectory() as td:
        out = hybrid_search(Path(td), "anything", top_k=5)
        assert out.get("ok") is True
        assert out.get("hits") == []
