"""Phase C — pre-edit impact analysis (Cursor-like guard before write/edit).

Combines:
  - Tree-sitter symbol graph blast radius
  - Jedi project references (real static analysis)
  - Hybrid retrieval context around the target path
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .blast_radius import blast_radius
from .hybrid_retrieval import hybrid_search
from .persistent_index import get_or_build_graph


def _enabled() -> bool:
    return (os.getenv("CODE_INTEL_PREFLIGHT") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _symbol_hints_from_patch(old_string: str, new_string: str) -> list[str]:
    blob = f"{old_string or ''}\n{new_string or ''}"
    names = re.findall(
        r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b|\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(",
        blob,
    )
    out: list[str] = []
    for a, b in names:
        n = a or b
        if n and n not in out and n not in {"self", "cls", "print", "len", "range"}:
            out.append(n)
    return out[:8]


def analyze_edit_preflight(
    work_dir: str | Path,
    path: str,
    *,
    old_string: str = "",
    new_string: str = "",
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Return impact analysis that should be consulted before applying an edit."""
    if not _enabled():
        return {"ok": True, "skipped": True, "reason": "CODE_INTEL_PREFLIGHT=0"}

    root = Path(work_dir).resolve()
    rel = (path or "").strip().lstrip("/")
    hints = _symbol_hints_from_patch(old_string, new_string)
    report: dict[str, Any] = {
        "ok": True,
        "path": rel,
        "symbol_hints": hints,
        "engine": "preflight-jedi+tree-sitter+bm25",
    }

    try:
        graph = get_or_build_graph(root)
        report["graph_stats"] = graph.get("stats")
        report["graph_cached"] = bool(graph.get("from_cache"))
    except Exception as exc:
        graph = None
        report["graph_error"] = type(exc).__name__

    # Blast radius for file + each symbol hint
    impacts: list[dict[str, Any]] = []
    all_files: set[str] = set()
    try:
        br_file = blast_radius(root, path=rel, graph=graph, max_depth=3)
        impacts.append({"seed": rel, "kind": "file", **{k: br_file.get(k) for k in ("ok", "impacted_count", "impacted_files")}})
        all_files.update(br_file.get("impacted_files") or [])
        for h in hints[:5]:
            br = blast_radius(root, symbol_name=h, graph=graph, max_depth=3)
            impacts.append(
                {
                    "seed": h,
                    "kind": "symbol",
                    "ok": br.get("ok"),
                    "impacted_count": br.get("impacted_count"),
                    "impacted_files": (br.get("impacted_files") or [])[:15],
                }
            )
            all_files.update(br.get("impacted_files") or [])
    except Exception as exc:
        report["blast_error"] = type(exc).__name__
    report["blast"] = impacts
    report["impacted_files_union"] = sorted(all_files)[:40]
    report["impact_score"] = min(1.0, len(all_files) / 20.0)

    # Jedi references when line/col known or first def of hint in file
    jedi_block: dict[str, Any] = {}
    try:
        from .jedi_analysis import find_references

        fp = root / rel
        if fp.is_file() and rel.endswith(".py"):
            src = fp.read_text(encoding="utf-8", errors="replace")
            lines = src.splitlines()
            targets: list[tuple[int, int, str]] = []
            if line is not None and column is not None:
                targets.append((int(line), int(column), "cursor"))
            for h in hints[:3]:
                for i, ln in enumerate(lines, start=1):
                    if re.search(rf"\b{re.escape(h)}\b", ln):
                        col = ln.index(h) if h in ln else 0
                        targets.append((i, col, h))
                        break
            refs_summary = []
            for ln, col, label in targets[:4]:
                refs = find_references(root, rel, line=ln, column=col, source=src)
                refs_summary.append(
                    {
                        "label": label,
                        "line": ln,
                        "reference_count": refs.get("reference_count"),
                        "impacted_files": (refs.get("impacted_files") or [])[:15],
                    }
                )
                all_files.update(refs.get("impacted_files") or [])
            jedi_block = {"ok": True, "refs": refs_summary}
    except Exception as exc:
        jedi_block = {"ok": False, "error": type(exc).__name__}
    report["jedi"] = jedi_block
    report["impacted_files_union"] = sorted(all_files)[:40]
    report["impact_score"] = min(1.0, len(all_files) / 20.0)

    # Retrieval context for the edit
    try:
        q = " ".join(hints) if hints else rel
        hs = hybrid_search(root, q or rel, top_k=5, graph=graph)
        report["retrieval"] = {
            "hits": [
                {"name": h.get("name"), "path": h.get("path"), "score": h.get("score")}
                for h in (hs.get("hits") or [])[:5]
            ]
        }
    except Exception as exc:
        report["retrieval_error"] = type(exc).__name__

    # Risk label for agent
    score = float(report.get("impact_score") or 0)
    if score >= 0.6:
        report["risk"] = "high"
    elif score >= 0.25:
        report["risk"] = "medium"
    else:
        report["risk"] = "low"
    return report


__all__ = ["analyze_edit_preflight"]
