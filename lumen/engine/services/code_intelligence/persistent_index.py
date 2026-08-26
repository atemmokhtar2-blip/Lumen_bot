"""On-disk code intelligence index (graph + search corpus metadata)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .symbol_graph import build_symbol_graph


def index_path_for(root: str | Path, store_dir: str | Path | None = None) -> Path:
    root_p = Path(root).resolve()
    base = Path(store_dir) if store_dir else root_p / ".lumen_code_index"
    base.mkdir(parents=True, exist_ok=True)
    return base / "symbol_graph.json"


def build_and_save_index(root: str | Path, *, store_dir: str | Path | None = None, max_files: int = 2000) -> dict[str, Any]:
    graph = build_symbol_graph(root, max_files=max_files)
    path = index_path_for(root, store_dir)
    payload = {
        "version": 1,
        "built_at": time.time(),
        "root": str(Path(root).resolve()),
        "graph": graph,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "path": str(path), "stats": graph.get("stats"), "engine": "persistent-tree-sitter"}


def load_index(root: str | Path, *, store_dir: str | Path | None = None) -> dict[str, Any] | None:
    path = index_path_for(root, store_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_or_build_graph(root: str | Path, *, store_dir: str | Path | None = None, rebuild: bool = False) -> dict[str, Any]:
    if not rebuild:
        cached = load_index(root, store_dir=store_dir)
        if cached and isinstance(cached.get("graph"), dict):
            g = cached["graph"]
            g["from_cache"] = True
            return g
    info = build_and_save_index(root, store_dir=store_dir)
    g = load_index(root, store_dir=store_dir)["graph"]  # type: ignore
    g["from_cache"] = False
    g["index_path"] = info["path"]
    return g


__all__ = ["build_and_save_index", "load_index", "get_or_build_graph", "index_path_for"]
