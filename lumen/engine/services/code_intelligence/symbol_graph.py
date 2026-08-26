"""Phase C — Symbol graph built from Tree-sitter symbols + call/import edges."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .tree_sitter_index import index_python_repo, parse_python_source


def build_symbol_graph(root: str | Path, *, max_files: int = 2000) -> dict[str, Any]:
    idx = index_python_repo(root, max_files=max_files)
    symbols = idx["symbols"]
    nodes = {s["id"]: s for s in symbols}
    edges: list[dict[str, str]] = []

    # contains edges from parent_id
    for s in symbols:
        if s.get("parent_id") and s["parent_id"] in nodes:
            edges.append({"src": s["parent_id"], "dst": s["id"], "rel": "contains"})

    # import edges: module -> imported name (best-effort)
    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for s in symbols:
        if s["kind"] in {"function", "method", "class", "module"}:
            name_to_ids[s["name"].split(".")[-1]].append(s["id"])

    root_p = Path(root).resolve()
    for s in symbols:
        if s["kind"] != "import":
            continue
        raw = str((s.get("extras") or {}).get("raw") or s["name"])
        # from x import y / import x
        m = re.search(r"from\s+([\w.]+)\s+import\s+([\w,\s*]+)", raw)
        if m:
            for part in m.group(2).split(","):
                name = part.strip().split(" as ")[0].strip()
                if not name or name == "*":
                    continue
                for tid in name_to_ids.get(name, [])[:5]:
                    edges.append({"src": s["id"], "dst": tid, "rel": "imports"})
        else:
            m2 = re.search(r"import\s+([\w.]+)", raw)
            if m2:
                mod = m2.group(1).split(".")[-1]
                for tid in name_to_ids.get(mod, [])[:5]:
                    edges.append({"src": s["id"], "dst": tid, "rel": "imports"})

    # call edges via official tree-sitter Query (not regex)
    try:
        from .ts_queries import extract_calls_and_defs
    except Exception:
        extract_calls_and_defs = None  # type: ignore
    if extract_calls_and_defs is not None:
        # map path -> list of function symbols covering lines
        by_path_funcs: dict[str, list[dict]] = defaultdict(list)
        for s in symbols:
            if s["kind"] in {"function", "method"}:
                by_path_funcs[s["path"]].append(s)
        for path, funcs in by_path_funcs.items():
            fp = root_p / path
            if not fp.is_file():
                continue
            try:
                raw = fp.read_bytes()
            except OSError:
                continue
            extracted = extract_calls_and_defs(raw, path=path)
            for call in extracted.get("calls") or []:
                callee = call.get("name") or ""
                if callee in {"print", "len", "range", "str", "int", "list", "dict", "set", "type"}:
                    continue
                line = int(call.get("line") or 0)
                # attribute callee: take last segment
                simple = callee.split(".")[-1]
                caller_id = None
                for fn in funcs:
                    if int(fn["start_line"]) <= line <= int(fn["end_line"]):
                        caller_id = fn["id"]
                        break
                if not caller_id:
                    continue
                for tid in name_to_ids.get(simple, [])[:3]:
                    if tid != caller_id:
                        edges.append({"src": caller_id, "dst": tid, "rel": "calls"})

    # dedupe edges
    seen = set()
    uniq = []
    for e in edges:
        key = (e["src"], e["dst"], e["rel"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    return {
        "root": idx["root"],
        "files_indexed": idx["files_indexed"],
        "nodes": list(nodes.values()),
        "edges": uniq,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(uniq),
            "by_kind": _count_kind(symbols),
            "by_rel": _count_rel(uniq),
        },
        "engine": "tree-sitter-graph",
        "errors": idx.get("errors") or [],
    }


def _count_kind(symbols: list[dict]) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for s in symbols:
        c[s["kind"]] += 1
    return dict(c)


def _count_rel(edges: list[dict]) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for e in edges:
        c[e["rel"]] += 1
    return dict(c)


__all__ = ["build_symbol_graph"]
