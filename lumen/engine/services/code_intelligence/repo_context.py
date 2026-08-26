"""Large-repo context packing for the coding agent (real retrieval, not heuristics-only).

Uses:
  - Tree-sitter / symbol graph (persistent index)
  - Hybrid BM25 + vector retrieval
  - Blast-radius for seeds mentioned in the goal
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _max_files() -> int:
    try:
        return max(4, min(40, int(os.getenv("CODE_INTEL_CONTEXT_FILES") or "16")))
    except ValueError:
        return 16


def _max_bytes() -> int:
    try:
        return max(800, min(12000, int(os.getenv("CODE_INTEL_CONTEXT_BYTES") or "3500")))
    except ValueError:
        return 3500


def pack_repo_context_for_goal(
    work_dir: str | Path,
    goal: str,
    *,
    extra_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Select the most relevant files for a goal on a large tree.

    Returns structure consumable by agent_loop / Builder IR metadata.
    """
    root = Path(work_dir).resolve()
    out: dict[str, Any] = {
        "ok": False,
        "root": str(root),
        "file_list": [],
        "files": {},
        "retrieval": {},
        "graph_stats": {},
        "engine": "hybrid+graph",
        "errors": [],
    }
    if not root.is_dir():
        out["errors"].append("not_a_dir")
        return out

    py_count = 0
    try:
        for p in root.rglob("*.py"):
            if any(x in p.parts for x in (".git", "__pycache__", ".venv", "venv", "node_modules")):
                continue
            py_count += 1
            if py_count > 5000:
                break
    except Exception:
        py_count = 0
    out["py_file_count"] = py_count

    # Always include entrypoints if present
    seeds: list[str] = []
    for name in ("main.py", "bot.py", "app.py", "src/main.py"):
        if (root / name).is_file():
            seeds.append(name)
    for ep in extra_paths or []:
        if ep and (root / ep).is_file() and ep not in seeds:
            seeds.append(ep)

    hits: list[dict[str, Any]] = []
    try:
        from .hybrid_retrieval import hybrid_search
        q = (goal or "").strip()[:2000] or "main entry handlers"
        raw = hybrid_search(str(root), q, top_k=max(8, _max_files()))
        out["retrieval"] = {
            "ok": bool(raw.get("ok", True)) if isinstance(raw, dict) else True,
            "engine": (raw.get("engine") if isinstance(raw, dict) else None),
        }
        if isinstance(raw, dict):
            for h in raw.get("hits") or raw.get("results") or []:
                if isinstance(h, dict):
                    path = str(h.get("path") or h.get("file") or h.get("id") or "")
                    if path:
                        hits.append({"path": path, "score": h.get("score"), "snippet": str(h.get("snippet") or h.get("text") or "")[:400]})
                elif isinstance(h, str):
                    hits.append({"path": h})
        out["retrieval"]["hit_count"] = len(hits)
    except Exception as exc:
        out["errors"].append(f"hybrid:{type(exc).__name__}")
        logger.exception("hybrid_search failed in pack_repo_context")

    try:
        from .persistent_index import get_or_build_graph
        graph = get_or_build_graph(root)
        out["graph_stats"] = graph.get("stats") or {
            "symbols": len(graph.get("symbols") or graph.get("nodes") or []),
        }
        out["graph_cached"] = bool(graph.get("from_cache"))
    except Exception as exc:
        out["errors"].append(f"graph:{type(exc).__name__}")

    # Rank paths: seeds first, then retrieval hits
    ordered: list[str] = []
    for s in seeds:
        if s not in ordered:
            ordered.append(s)
    for h in hits:
        path = str(h.get("path") or "").replace("\\", "/").lstrip("./")
        if not path or path in ordered:
            continue
        if path.endswith((".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs")):
            ordered.append(path)
        if len(ordered) >= _max_files():
            break

    # Fill with top-level modules if still sparse
    if len(ordered) < 4:
        for p in sorted(root.glob("*.py"))[:8]:
            rel = p.name
            if rel not in ordered:
                ordered.append(rel)

    files: dict[str, str] = {}
    max_b = _max_bytes()
    for rel in ordered[: _max_files()]:
        fp = root / rel
        if not fp.is_file():
            # try basename match from hit
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            out["errors"].append(f"read:{rel}:{type(exc).__name__}")
            continue
        if len(text) > max_b:
            text = text[:max_b] + f"\n...[truncated {len(text)} chars]"
        files[rel] = text

    out["file_list"] = list(files.keys())
    out["files"] = files
    out["ok"] = bool(files) or py_count == 0  # empty new project still ok
    out["hits"] = hits[:12]
    return out


def context_to_agent_block(ctx: dict[str, Any]) -> str:
    if not ctx:
        return ""
    lines = [
        "--- REPO_CONTEXT (hybrid retrieval + graph) ---",
        f"py_files≈{ctx.get('py_file_count')} graph={ctx.get('graph_stats')}",
    ]
    for path, body in list((ctx.get("files") or {}).items())[: _max_files()]:
        lines.append(f"\n### FILE {path}\n{body}")
    if ctx.get("hits"):
        lines.append("\n### RETRIEVAL_HITS")
        for h in (ctx.get("hits") or [])[:8]:
            lines.append(f"- {h.get('path')} score={h.get('score')}")
    lines.append("--- END_REPO_CONTEXT ---")
    return "\n".join(lines)[:24000]


__all__ = ["pack_repo_context_for_goal", "context_to_agent_block"]
