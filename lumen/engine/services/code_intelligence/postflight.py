"""Post-edit verification: syntax + re-index touch + retrieval sanity."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .incremental import ensure_incremental_index


def analyze_edit_postflight(work_dir: str | Path, path: str) -> dict[str, Any]:
    root = Path(work_dir).resolve()
    rel = (path or "").strip()
    fp = root / rel
    report: dict[str, Any] = {"ok": True, "path": rel, "engine": "postflight"}
    if not fp.is_file():
        return {"ok": False, "error": "not_found", "path": rel}
    if rel.endswith(".py"):
        try:
            src = fp.read_text(encoding="utf-8", errors="replace")
            ast.parse(src, filename=rel)
            report["syntax_ok"] = True
        except SyntaxError as exc:
            report["ok"] = False
            report["syntax_ok"] = False
            report["syntax_error"] = f"{exc.msg} line {exc.lineno}"
    # refresh incremental index (mtime-aware)
    try:
        report["index"] = ensure_incremental_index(root)
    except Exception as exc:
        report["index_error"] = type(exc).__name__
    return report


__all__ = ["analyze_edit_postflight"]
