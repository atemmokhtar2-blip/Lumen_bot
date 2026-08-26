"""Phase C — Hybrid retrieval: BM25 + vector (local or external embeddings)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from .embeddings import cosine, embed_text_local, embed_texts, tokenize_code
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
        return {"ok": True, "hits": [], "query": query, "engine": "hybrid-bm25-vector-rrf-store"}

    tokenized = [tokenize_code(d["text"]) for d in docs]
    bm25 = BM25Okapi(tokenized)
    q_toks = tokenize_code(query)
    bm25_scores = list(bm25.get_scores(q_toks))
    # normalize bm25
    max_b = max(bm25_scores) if bm25_scores else 1.0
    max_b = max_b or 1.0
    # Prefer real embeddings (Voyage / fastembed) via embed_texts; hash only as last resort
    try:
        emb = embed_texts([query] + [d["text"] for d in docs])
        vectors = list(emb.get("vectors") or [])
        if len(vectors) == 1 + len(docs) and all(isinstance(v, (list, tuple)) and v for v in vectors):
            q_vec = list(map(float, vectors[0]))
            doc_vecs = [list(map(float, v)) for v in vectors[1:]]
            emb_provider = emb.get("provider") or emb.get("fallback") or "embed_texts"
        else:
            raise RuntimeError("embed_texts_incomplete")
    except Exception as _emb_exc:
        import os as _os
        required = (_os.getenv("CODE_EMBEDDING_REQUIRED") or "").strip().lower() in {"1", "true", "yes"}
        prod = (_os.getenv("ENVIRONMENT") or "").strip().lower() in {"production", "prod", "staging"}
        if required or (prod and (_os.getenv("CODE_EMBEDDING_REQUIRED") or "1") != "0"):
            # Production default: do not silently degrade to hash vectors
            return {
                "ok": False,
                "hits": [],
                "query": query,
                "engine": "hybrid-bm25-vector-rrf-store",
                "embed_provider": "unavailable",
                "error": f"embeddings_required:{type(_emb_exc).__name__}:{_emb_exc}",
            }
        q_vec = embed_text_local(query)
        doc_vecs = [embed_text_local(d["text"]) for d in docs]
        emb_provider = "hash_local_fallback"
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
    # Merge persistent vector store hits (world-class path)
    try:
        from .vector_store import CodeVectorStore
        store = CodeVectorStore(root_p)
        vhits = store.search(query, top_k=top_k)
        # RRF merge with existing hits
        k = 60
        scores: dict[str, float] = {}
        meta: dict[str, dict] = {}
        for r, h in enumerate(hits, start=1):
            key = str(h.get("id") or f"{h.get('path')}:{h.get('name')}")
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + r)
            meta[key] = h
        for r, h in enumerate(vhits, start=1):
            key = str(h.get("id") or f"{h.get('path')}:{h.get('name')}")
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + r)
            if key not in meta:
                meta[key] = {
                    "id": h.get("id"),
                    "name": h.get("name"),
                    "path": h.get("path"),
                    "kind": h.get("kind"),
                    "score": h.get("score"),
                    "start_line": h.get("start_line"),
                }
        merged = []
        for key, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
            row = dict(meta[key])
            row["score"] = round(sc, 6)
            row.pop("text", None)
            merged.append(row)
        hits = merged[: max(1, min(top_k, 50))]
    except Exception:
        pass
    # strip heavy text from hits
    for h in hits:
        h.pop("text", None)
    return {
        "ok": True,
        "query": query,
        "hits": hits,
        "embed_provider": emb_provider,
        "corpus_size": len(docs),
        "engine": "hybrid-bm25-vector-rrf",
        "graph_stats": graph.get("stats"),
    }


__all__ = ["hybrid_search"]
