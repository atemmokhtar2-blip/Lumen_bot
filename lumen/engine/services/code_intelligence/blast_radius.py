"""Phase C — Blast-radius analysis before edit (who depends on this symbol/file)."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .symbol_graph import build_symbol_graph


def blast_radius(
    root: str | Path,
    *,
    path: str = "",
    symbol_name: str = "",
    max_depth: int = 3,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    graph = graph or build_symbol_graph(root)
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    # reverse edges: dst <- src for calls/imports/contains
    rev: dict[str, list[tuple[str, str]]] = defaultdict(list)
    fwd: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in graph.get("edges") or []:
        rev[e["dst"]].append((e["src"], e["rel"]))
        fwd[e["src"]].append((e["dst"], e["rel"]))

    seeds = []
    for n in nodes.values():
        if path and n.get("path") == path:
            seeds.append(n["id"])
        if symbol_name and (
            n.get("name") == symbol_name
            or str(n.get("name") or "").endswith("." + symbol_name)
        ):
            seeds.append(n["id"])
    seeds = list(dict.fromkeys(seeds))
    if not seeds:
        return {
            "ok": False,
            "error": "no_seed_symbol",
            "path": path,
            "symbol_name": symbol_name,
            "impacted": [],
        }

    impacted: dict[str, dict[str, Any]] = {}
    q: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    seen = set(seeds)
    for s in seeds:
        impacted[s] = {"id": s, "depth": 0, "via": "seed", **{k: nodes[s].get(k) for k in ("kind", "name", "path")}}

    while q:
        cur, depth = q.popleft()
        if depth >= max_depth:
            continue
        for pred, rel in rev.get(cur, []):
            if pred in seen:
                continue
            seen.add(pred)
            meta = nodes.get(pred) or {}
            impacted[pred] = {
                "id": pred,
                "depth": depth + 1,
                "via": rel,
                "kind": meta.get("kind"),
                "name": meta.get("name"),
                "path": meta.get("path"),
            }
            q.append((pred, depth + 1))

    files = sorted({i.get("path") for i in impacted.values() if i.get("path")})
    return {
        "ok": True,
        "seeds": seeds,
        "impacted": list(impacted.values()),
        "impacted_count": len(impacted),
        "impacted_files": files,
        "max_depth": max_depth,
        "engine": "symbol-graph-blast-radius",
    }


__all__ = ["blast_radius"]
