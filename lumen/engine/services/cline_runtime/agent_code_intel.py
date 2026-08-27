"""Agent-facing code intelligence tools (tree-sitter symbol graph + hybrid search).

World-class coding agents use structural navigation, not grep alone:
  find_symbol → get_symbol_source → blast_radius → edit

Backed by lumen.engine.services.code_intelligence (official tree-sitter graph).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _root(work_dir: str | Path) -> Path:
    return Path(work_dir).resolve()


def _graph(work_dir: str | Path, *, rebuild: bool = False) -> dict[str, Any]:
    try:
        from lumen.engine.services.code_intelligence.persistent_index import get_or_build_graph
        return get_or_build_graph(work_dir, rebuild=rebuild)
    except Exception:
        from lumen.engine.services.code_intelligence.symbol_graph import build_symbol_graph
        return build_symbol_graph(work_dir)


def find_symbol(
    work_dir: str,
    name: str,
    *,
    kind: str = "",
    path_prefix: str = "",
    max_results: int = 30,
) -> dict[str, Any]:
    """Find definitions by symbol name (AST/symbol-graph, not text grep)."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name_required"}
    try:
        g = _graph(work_dir)
        nodes = list(g.get("nodes") or [])
        hits: list[dict[str, Any]] = []
        name_l = name.lower()
        for n in nodes:
            if n.get("kind") in {"module"} and not kind:
                continue
            nm = str(n.get("name") or "")
            if nm != name and name_l not in nm.lower():
                continue
            if kind and str(n.get("kind") or "") != kind:
                continue
            path = str(n.get("path") or "")
            if path_prefix and not path.startswith(path_prefix):
                continue
            hits.append({
                "id": n.get("id"),
                "name": nm,
                "kind": n.get("kind"),
                "path": path,
                "start_line": n.get("start_line"),
                "end_line": n.get("end_line"),
                "exact": nm == name,
            })
        # exact matches first
        hits.sort(key=lambda h: (0 if h.get("exact") else 1, h.get("path") or ""))
        hits = hits[: max(1, min(max_results, 100))]
        return {
            "ok": True,
            "query": name,
            "symbols": hits,
            "count": len(hits),
            "engine": "symbol-graph",
        }
    except Exception as exc:
        logger.exception("find_symbol failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def get_symbol_source(
    work_dir: str,
    *,
    name: str = "",
    path: str = "",
    symbol_id: str = "",
    max_lines: int = 200,
) -> dict[str, Any]:
    """Return source lines for a symbol (definition body)."""
    try:
        g = _graph(work_dir)
        nodes = {n["id"]: n for n in (g.get("nodes") or []) if n.get("id")}
        target = None
        if symbol_id and symbol_id in nodes:
            target = nodes[symbol_id]
        elif name:
            for n in nodes.values():
                if n.get("name") == name and (not path or n.get("path") == path):
                    target = n
                    break
            if target is None:
                for n in nodes.values():
                    if str(n.get("name") or "") == name:
                        target = n
                        break
        if target is None:
            return {"ok": False, "error": "symbol_not_found", "name": name, "path": path}
        rel = str(target.get("path") or "")
        root = _root(work_dir)
        fp = root / rel
        if not fp.is_file():
            return {"ok": False, "error": "file_missing", "path": rel}
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        a = max(1, int(target.get("start_line") or 1))
        b = min(len(lines), int(target.get("end_line") or a))
        if b - a + 1 > max_lines:
            b = a + max_lines - 1
        body = "\n".join(lines[a - 1 : b])
        return {
            "ok": True,
            "name": target.get("name"),
            "kind": target.get("kind"),
            "path": rel,
            "start_line": a,
            "end_line": b,
            "source": body,
            "id": target.get("id"),
            "engine": "symbol-graph",
        }
    except Exception as exc:
        logger.exception("get_symbol_source failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def find_references(
    work_dir: str,
    name: str,
    *,
    max_results: int = 40,
) -> dict[str, Any]:
    """Find call/reference sites via symbol-graph edges (+ optional Jedi)."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name_required"}
    try:
        g = _graph(work_dir)
        nodes = {n["id"]: n for n in (g.get("nodes") or []) if n.get("id")}
        # definitions matching name
        defs = [n for n in nodes.values() if n.get("name") == name and n.get("kind") in {"function", "method", "class"}]
        def_ids = {n["id"] for n in defs}
        refs: list[dict[str, Any]] = []
        for e in g.get("edges") or []:
            if e.get("rel") not in {"calls", "imports", "references", "uses"}:
                continue
            dst = e.get("dst")
            src = e.get("src")
            if dst in def_ids:
                sn = nodes.get(src) or {}
                refs.append({
                    "from_name": sn.get("name"),
                    "from_kind": sn.get("kind"),
                    "from_path": sn.get("path"),
                    "from_line": sn.get("start_line"),
                    "rel": e.get("rel"),
                    "to_name": name,
                })
            if src in def_ids and e.get("rel") == "calls":
                # outbound calls from the symbol — still useful
                dn = nodes.get(dst) or {}
                refs.append({
                    "from_name": name,
                    "from_kind": (nodes.get(src) or {}).get("kind"),
                    "from_path": (nodes.get(src) or {}).get("path"),
                    "from_line": (nodes.get(src) or {}).get("start_line"),
                    "rel": "calls_out",
                    "to_name": dn.get("name"),
                    "to_path": dn.get("path"),
                })
        # Jedi enrichment when installed
        try:
            from lumen.engine.services.code_intelligence.jedi_analysis import find_references as jedi_refs
            if jedi_refs and defs:
                d0 = defs[0]
                jr = jedi_refs(work_dir, str(d0.get("path") or ""), int(d0.get("start_line") or 1), 0)
                if isinstance(jr, dict) and jr.get("references"):
                    for r in list(jr["references"])[:20]:
                        refs.append({"jedi": True, **(r if isinstance(r, dict) else {"raw": str(r)})})
        except Exception:
            pass
        refs = refs[: max(1, min(max_results, 100))]
        return {
            "ok": True,
            "name": name,
            "definitions": [
                {"id": d.get("id"), "path": d.get("path"), "start_line": d.get("start_line"), "kind": d.get("kind")}
                for d in defs
            ],
            "references": refs,
            "count": len(refs),
            "engine": "symbol-graph",
        }
    except Exception as exp:
        logger.exception("find_references failed")
        return {"ok": False, "error": f"{type(exp).__name__}:{exp}"}


def symbol_blast_radius(
    work_dir: str,
    *,
    name: str = "",
    path: str = "",
    max_depth: int = 3,
) -> dict[str, Any]:
    """Impact analysis before multi-file edits (who depends on this symbol/file)."""
    try:
        from lumen.engine.services.code_intelligence.blast_radius import blast_radius
        return blast_radius(
            work_dir,
            path=path or "",
            symbol_name=name or "",
            max_depth=max(1, min(int(max_depth or 3), 8)),
        )
    except Exception as exc:
        logger.exception("blast_radius failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def code_search(
    work_dir: str,
    query: str,
    *,
    top_k: int = 10,
) -> dict[str, Any]:
    """Hybrid BM25 + structural retrieval over the symbol index."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query_required"}
    try:
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        hits = hybrid_search(work_dir, query, top_k=max(1, min(int(top_k or 10), 30)))
        if isinstance(hits, dict):
            return {"ok": True, **hits, "engine": "hybrid"}
        return {"ok": True, "results": list(hits or []), "engine": "hybrid"}
    except Exception as exc:
        logger.exception("code_search failed")
        # fallback: find_symbol on first token
        tok = query.split()[0] if query.split() else query
        return find_symbol(work_dir, tok)


__all__ = [
    "find_symbol",
    "get_symbol_source",
    "find_references",
    "symbol_blast_radius",
    "code_search",
]
