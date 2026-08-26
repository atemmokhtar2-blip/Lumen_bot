"""Phase C — Hybrid retrieval: BM25 + vector (local or external embeddings)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from .embeddings import cosine, embed_text_local, tokenize_code
from .symbol_graph import build_symbol_graph


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
                a = max(0, int(node["start_line"]) - 1)
                b = min(len(lines), int(node["end_line"]))
                snippet = "\n".join(lines[a:b])[:4000]
            except OSError:
                snippet = node.get("name") or ""
        else:
            snippet = node.get("name") or ""
        text = f"{node.get('kind')} {node.get('name')} {path}\n{snippet}"
        docs.append(
            {
                "id": node["id"],
                "kind": node["kind"],
                "name": node["name"],
                "path": path,
                "text": text,
                "start_line": node.get("start_line"),
                "end_line": node.get("end_line"),
            }
        )
    return docs


def hybrid_search(
    root: str | Path,
    query: str,
    *,
    top_k: int = 10,
    graph: dict[str, Any] | None = None,
    bm25_weight: float = 0.55,
    vector_weight: float = 0.45,
) -> dict[str, Any]:
    root_p = Path(root).resolve()
    graph = graph or build_symbol_graph(root_p)
    docs = _corpus_from_graph(graph, root_p)
    if not docs:
        return {"ok": True, "hits": [], "query": query, "engine": "hybrid-bm25-vector-rrf"}

    tokenized = [tokenize_code(d["text"]) for d in docs]
    bm25 = BM25Okapi(tokenized)
    q_toks = tokenize_code(query)
    bm25_scores = list(bm25.get_scores(q_toks))
    # normalize bm25
    max_b = max(bm25_scores) if bm25_scores else 1.0
    max_b = max_b or 1.0
    q_vec = embed_text_local(query)
    doc_vecs = [embed_text_local(d["text"]) for d in docs]
    vec_scores = [cosine(q_vec, v) for v in doc_vecs]

    # Reciprocal Rank Fusion (RRF) — stronger hybrid than linear mix alone
    bm25_order = sorted(range(len(docs)), key=lambda i: bm25_scores[i], reverse=True)
    vec_order = sorted(range(len(docs)), key=lambda i: vec_scores[i], reverse=True)
    bm25_rank = {i: r for r, i in enumerate(bm25_order, start=1)}
    vec_rank = {i: r for r, i in enumerate(vec_order, start=1)}
    k_rrf = 60
    ranked = []
    for i, d in enumerate(docs):
        rrf = 1.0 / (k_rrf + bm25_rank[i]) + 1.0 / (k_rrf + vec_rank[i])
        linear = bm25_weight * (bm25_scores[i] / max_b) + vector_weight * max(0.0, vec_scores[i])
        score = 0.7 * rrf + 0.3 * linear
        ranked.append(
            {
                **d,
                "score": round(float(score), 6),
                "rrf": round(float(rrf), 6),
                "bm25": round(float(bm25_scores[i]), 4),
                "vec": round(float(vec_scores[i]), 4),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    hits = ranked[: max(1, min(top_k, 50))]
    # strip heavy text from hits
    for h in hits:
        h.pop("text", None)
    return {
        "ok": True,
        "query": query,
        "hits": hits,
        "corpus_size": len(docs),
        "engine": "hybrid-bm25-vector-rrf",
        "graph_stats": graph.get("stats"),
    }


__all__ = ["hybrid_search"]
