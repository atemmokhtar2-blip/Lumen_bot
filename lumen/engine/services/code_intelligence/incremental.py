"""Incremental code index: only re-parse files whose mtime changed."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .multi_lang import index_repo_multi
from .symbol_graph import build_symbol_graph
from .vector_store import build_vector_index_from_symbols


def _mtime_map(root: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".py", ".js", ".jsx", ".mjs", ".cjs"}:
            continue
        if any(x in p.parts for x in {".git", "node_modules", ".venv", "__pycache__", ".lumen_code_index"}):
            continue
        try:
            out[p.relative_to(root).as_posix()] = p.stat().st_mtime
        except OSError:
            continue
    return out


def ensure_incremental_index(
    root: str | Path,
    *,
    store_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root_p = Path(root).resolve()
    base = Path(store_dir) if store_dir else root_p / ".lumen_code_index"
    base.mkdir(parents=True, exist_ok=True)
    stamp_path = base / "mtime_stamp.json"
    prev = {}
    if stamp_path.is_file() and not force:
        try:
            prev = json.loads(stamp_path.read_text(encoding="utf-8")).get("mtimes") or {}
        except Exception:
            prev = {}
    cur = _mtime_map(root_p)
    changed = [k for k, v in cur.items() if prev.get(k) != v]
    deleted = [k for k in prev if k not in cur]
    need = force or (not (base / "symbol_graph.json").is_file()) or bool(changed) or bool(deleted)

    if not need:
        return {
            "ok": True,
            "rebuilt": False,
            "changed_files": 0,
            "engine": "incremental-skip",
        }

    multi = index_repo_multi(root_p)
    # also build python-centric graph for edges
    graph = build_symbol_graph(root_p)
    # merge multi-lang symbols into graph nodes (union by id)
    nodes = {n["id"]: n for n in graph.get("nodes") or []}
    for s in multi.get("symbols") or []:
        nodes[s["id"]] = s
    graph["nodes"] = list(nodes.values())
    graph["stats"] = {
        **(graph.get("stats") or {}),
        "node_count": len(nodes),
        "multi_lang_files": multi.get("files_indexed"),
        "by_lang": multi.get("by_lang"),
    }
    payload = {
        "version": 2,
        "built_at": time.time(),
        "root": str(root_p),
        "graph": graph,
        "multi": {"files_indexed": multi.get("files_indexed"), "by_lang": multi.get("by_lang")},
    }
    (base / "symbol_graph.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    vec = build_vector_index_from_symbols(root_p, list(nodes.values()), store_dir=base)
    stamp_path.write_text(
        json.dumps({"mtimes": cur, "updated_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "rebuilt": True,
        "changed_files": len(changed),
        "deleted_files": len(deleted),
        "files_indexed": multi.get("files_indexed"),
        "by_lang": multi.get("by_lang"),
        "vector": vec,
        "engine": "incremental-tree-sitter-vector",
        "product_scope": multi.get("product_scope"),
    }


__all__ = ["ensure_incremental_index"]
