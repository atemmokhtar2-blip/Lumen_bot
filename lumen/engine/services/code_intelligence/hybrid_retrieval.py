"""World-class hybrid code retrieval (2026 production baseline).

Pipeline (research consensus 2026):
  1) BM25 sparse  — exact identifiers / rare tokens
  2) Dense vectors — paraphrase / semantic (Voyage code-4 / fastembed / local)
  3) Graph boost  — 1-hop neighbors of name matches on the AST symbol graph
  4) Reciprocal Rank Fusion (RRF, k=60) — fuse ranks, never raw score averages
  5) Rerank top-N — Voyage rerank API when keyed, else structural local rerank

References: RRF k=60 default; hybrid+rerank is the 2026 RAG baseline for code agents.
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from .embeddings import cosine, embed_text_local, embed_query, embed_documents, tokenize_code
from .symbol_graph import build_symbol_graph

logger = logging.getLogger(__name__)

_RRF_K = 60
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _corpus_from_graph(graph: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if node.get("kind") not in {"function", "method", "class", "module"}:
            continue
        path = str(node.get("path") or "")
        snippet = ""
        fp = root / path
        if fp.is_file() and node.get("kind") in {"function", "method", "class"}:
            try:
                lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                a = max(0, int(node.get("start_line") or 1) - 1)
                b = min(len(lines), int(node.get("end_line") or a + 1))
                snippet = "\n".join(lines[a:b])[:4000]
            except OSError:
                snippet = str(node.get("name") or "")
        else:
            snippet = str(node.get("name") or "")
        text = f"{node.get('kind')} {node.get('name')} {path}\n{snippet}"
        docs.append(
            {
                "id": str(node.get("id") or ""),
                "kind": node.get("kind"),
                "name": node.get("name"),
                "path": path,
                "text": text,
                "start_line": node.get("start_line"),
                "end_line": node.get("end_line"),
            }
        )
    return docs


def _rrf_fuse(
    ranked_lists: list[list[int]],
    *,
    k: int = _RRF_K,
) -> dict[int, float]:
    """Reciprocal Rank Fusion over lists of doc indices (best first)."""
    scores: dict[int, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, doc_i in enumerate(ranked):
            scores[int(doc_i)] += 1.0 / (k + rank + 1)
    return dict(scores)


def _bm25_ranking(docs: list[dict[str, Any]], query: str) -> tuple[list[float], list[int]]:
    tokenized = [tokenize_code(d["text"]) for d in docs]
    bm25 = BM25Okapi(tokenized)
    q_toks = tokenize_code(query)
    scores = list(bm25.get_scores(q_toks))
    order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return scores, order


def _dense_ranking(
    docs: list[dict[str, Any]], query: str
) -> tuple[list[float], list[int], str]:
    """Dense channel: query with input_type=query, docs with document (Voyage-correct)."""
    try:
        q_out = embed_query(query)
        d_out = embed_documents([d["text"] for d in docs])
        if not q_out.get("ok") or not d_out.get("ok"):
            raise RuntimeError(
                f"embed_failed:q={q_out.get('error')};d={d_out.get('error')}"
            )
        q_vec = list(map(float, q_out.get("vector") or (q_out.get("vectors") or [[]])[0]))
        doc_vecs = [list(map(float, v)) for v in (d_out.get("vectors") or [])]
        if not q_vec or len(doc_vecs) != len(docs):
            raise RuntimeError("embed_vectors_incomplete")
        provider = str(q_out.get("provider") or d_out.get("provider") or "neural")
    except Exception as exc:
        required = (os.getenv("CODE_EMBEDDING_REQUIRED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        prod = (os.getenv("ENVIRONMENT") or "").strip().lower() in {
            "production",
            "prod",
            "staging",
        }
        if required or (
            prod and (os.getenv("CODE_EMBEDDING_REQUIRED") or "1") != "0"
        ):
            raise RuntimeError(f"embeddings_required:{type(exc).__name__}:{exc}") from exc
        q_vec = embed_text_local(query)
        doc_vecs = [embed_text_local(d["text"]) for d in docs]
        provider = "hash_local_fallback"
    scores = [cosine(q_vec, v) for v in doc_vecs]
    order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return scores, order, provider


def _graph_ranking(
    docs: list[dict[str, Any]],
    graph: dict[str, Any],
    query: str,
) -> list[int]:
    """Rank docs by graph proximity to query name tokens (1-hop boost)."""
    id_to_idx = {d["id"]: i for i, d in enumerate(docs) if d.get("id")}
    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        nm = str(d.get("name") or "").lower()
        if nm:
            name_to_ids[nm].append(str(d["id"]))
            # last segment of qualified names
            if "." in nm:
                name_to_ids[nm.rsplit(".", 1)[-1]].append(str(d["id"]))

    # adjacency undirected for boost
    adj: dict[str, set[str]] = defaultdict(set)
    for e in graph.get("edges") or []:
        s, d = str(e.get("src") or ""), str(e.get("dst") or "")
        if s and d:
            adj[s].add(d)
            adj[d].add(s)

    q_toks = {t.lower() for t in _IDENT.findall(query or "")}
    scores: dict[int, float] = defaultdict(float)
    for tok in q_toks:
        seeds = name_to_ids.get(tok) or []
        for sid in seeds:
            if sid in id_to_idx:
                scores[id_to_idx[sid]] += 3.0  # direct name hit
            for nb in adj.get(sid) or []:
                if nb in id_to_idx:
                    scores[id_to_idx[nb]] += 1.0  # 1-hop neighbor

    if not scores:
        return list(range(len(docs)))  # neutral order
    return sorted(scores.keys(), key=lambda i: scores[i], reverse=True) + [
        i for i in range(len(docs)) if i not in scores
    ]


def _voyage_rerank(
    query: str, candidates: list[dict[str, Any]], *, top_n: int
) -> list[dict[str, Any]] | None:
    """Official Voyage rerank API when VOYAGE_API_KEY is set."""
    key = (os.getenv("VOYAGE_API_KEY") or os.getenv("CODE_EMBEDDING_API_KEY") or "").strip()
    if not key:
        return None
    try:
        import requests

        model = (os.getenv("CODE_RERANK_MODEL") or "rerank-2").strip()
        documents = [c.get("text") or f"{c.get('name')} {c.get('path')}" for c in candidates]
        resp = requests.post(
            "https://api.voyageai.com/v1/rerank",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "query": query,
                "documents": documents,
                "model": model,
                "top_k": min(top_n, len(documents)),
            },
            timeout=45,
        )
        if resp.status_code >= 400:
            logger.warning("voyage rerank HTTP %s", resp.status_code)
            return None
        data = resp.json()
        order = []
        for row in data.get("data") or data.get("results") or []:
            idx = row.get("index")
            if idx is None:
                continue
            item = dict(candidates[int(idx)])
            item["rerank_score"] = float(row.get("relevance_score") or row.get("score") or 0.0)
            item["reranker"] = f"voyage:{model}"
            order.append(item)
        return order[:top_n] if order else None
    except Exception as exc:
        logger.debug("voyage rerank skipped: %s", exc)
        return None


def _local_rerank(
    query: str, candidates: list[dict[str, Any]], *, top_n: int
) -> list[dict[str, Any]]:
    """Structural rerank without external deps — exact name / path / kind boosts."""
    q = (query or "").lower()
    q_toks = {t.lower() for t in _IDENT.findall(query or "")}
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        base = float(c.get("score") or 0.0)
        name = str(c.get("name") or "").lower()
        path = str(c.get("path") or "").lower()
        boost = 0.0
        if name and name in q:
            boost += 2.0
        if name and name in q_toks:
            boost += 1.5
        for tok in q_toks:
            if tok and tok in path:
                boost += 0.4
            if tok and tok == name:
                boost += 1.0
        if str(c.get("kind") or "") in {"function", "method", "class"}:
            boost += 0.1
        item = dict(c)
        item["rerank_score"] = base + boost
        item["reranker"] = "local_structural"
        scored.append((item["rerank_score"], item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:top_n]]


def hybrid_search(
    root: str | Path,
    query: str,
    *,
    top_k: int = 10,
    graph: dict[str, Any] | None = None,
    bm25_weight: float = 0.55,  # kept for API compat; RRF is primary fusion
    vector_weight: float = 0.45,
    rrf_k: int = _RRF_K,
    rerank: bool = True,
    candidate_pool: int = 50,
) -> dict[str, Any]:
    """Hybrid code search: BM25 + dense + graph → RRF → optional rerank."""
    del bm25_weight, vector_weight  # RRF primary; weights retained for signature compat
    root_p = Path(root).resolve()
    graph = graph or build_symbol_graph(root_p)
    docs = _corpus_from_graph(graph, root_p)
    if not docs:
        return {
            "ok": True,
            "hits": [],
            "query": query,
            "engine": "hybrid-bm25-dense-graph-rrf-rerank",
            "channels": {},
        }

    try:
        bm25_scores, bm25_order = _bm25_ranking(docs, query)
        dense_scores, dense_order, emb_provider = _dense_ranking(docs, query)
        graph_order = _graph_ranking(docs, graph, query)
    except RuntimeError as exc:
        return {
            "ok": False,
            "hits": [],
            "query": query,
            "engine": "hybrid-bm25-dense-graph-rrf-rerank",
            "error": str(exc),
            "embed_provider": "unavailable",
        }

    rrf_scores = _rrf_fuse([bm25_order, dense_order, graph_order], k=max(1, int(rrf_k or _RRF_K)))
    # Full ranking by RRF
    fused_order = sorted(range(len(docs)), key=lambda i: rrf_scores.get(i, 0.0), reverse=True)

    pool_n = max(int(top_k), min(int(candidate_pool or 50), len(docs)))
    candidates: list[dict[str, Any]] = []
    for i in fused_order[:pool_n]:
        d = docs[i]
        candidates.append(
            {
                "id": d["id"],
                "kind": d["kind"],
                "name": d["name"],
                "path": d["path"],
                "start_line": d.get("start_line"),
                "end_line": d.get("end_line"),
                "text": d.get("text") or "",
                "score": round(float(rrf_scores.get(i, 0.0)), 6),
                "bm25": round(float(bm25_scores[i]), 4),
                "dense": round(float(dense_scores[i]), 4),
                "channels": {
                    "bm25_rank": bm25_order.index(i) + 1 if i in bm25_order else None,
                    "dense_rank": dense_order.index(i) + 1 if i in dense_order else None,
                    "graph_rank": graph_order.index(i) + 1 if i in graph_order else None,
                },
            }
        )

    reranker_used = "none"
    hits = candidates[: int(top_k)]
    if rerank and candidates:
        voyage_hits = _voyage_rerank(query, candidates, top_n=int(top_k))
        if voyage_hits is not None:
            hits = voyage_hits
            reranker_used = hits[0].get("reranker") if hits else "voyage"
        else:
            hits = _local_rerank(query, candidates, top_n=int(top_k))
            reranker_used = "local_structural"

    # Strip bulky text from final hits (agents need path/name/score)
    slim = []
    for h in hits:
        slim.append(
            {
                "id": h.get("id"),
                "kind": h.get("kind"),
                "name": h.get("name"),
                "path": h.get("path"),
                "start_line": h.get("start_line"),
                "end_line": h.get("end_line"),
                "score": h.get("rerank_score", h.get("score")),
                "bm25": h.get("bm25"),
                "dense": h.get("dense"),
                "channels": h.get("channels"),
                "reranker": h.get("reranker") or reranker_used,
            }
        )

    return {
        "ok": True,
        "hits": slim,
        "query": query,
        "engine": "hybrid-bm25-dense-graph-rrf-rerank",
        "embed_provider": emb_provider,
        "reranker": reranker_used,
        "rrf_k": int(rrf_k or _RRF_K),
        "channels": {"bm25": True, "dense": True, "graph": True},
        "pool": len(candidates),
    }


__all__ = ["hybrid_search"]
