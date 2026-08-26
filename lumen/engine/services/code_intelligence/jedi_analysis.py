"""Phase C — Jedi-based definitions & references (real static analysis, not regex).

Uses the official Jedi library: https://jedi.readthedocs.io/
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _project(root: Path):
    import jedi
    return jedi.Project(path=str(root))


def goto_definition(
    root: str | Path,
    path: str,
    *,
    line: int,
    column: int,
    source: str | None = None,
) -> dict[str, Any]:
    import jedi

    root_p = Path(root).resolve()
    fp = root_p / path
    code = source if source is not None else fp.read_text(encoding="utf-8", errors="replace")
    script = jedi.Script(code, path=str(fp), project=_project(root_p))
    defs = script.goto(line, column, follow_imports=True)
    out = []
    for d in defs:
        out.append(
            {
                "name": d.name,
                "type": d.type,
                "module_name": d.module_name,
                "path": str(Path(d.module_path).resolve().relative_to(root_p))
                if d.module_path and Path(d.module_path).is_relative_to(root_p)
                else (str(d.module_path) if d.module_path else None),
                "line": d.line,
                "column": d.column,
                "description": (d.description or "")[:200],
            }
        )
    return {"ok": True, "engine": "jedi", "path": path, "line": line, "column": column, "definitions": out}


def find_references(
    root: str | Path,
    path: str,
    *,
    line: int,
    column: int,
    source: str | None = None,
) -> dict[str, Any]:
    import jedi

    root_p = Path(root).resolve()
    fp = root_p / path
    code = source if source is not None else fp.read_text(encoding="utf-8", errors="replace")
    script = jedi.Script(code, path=str(fp), project=_project(root_p))
    refs = script.get_references(line, column, scope="project")
    out = []
    for r in refs:
        rel = None
        if r.module_path:
            try:
                rel = str(Path(r.module_path).resolve().relative_to(root_p))
            except ValueError:
                rel = str(r.module_path)
        out.append(
            {
                "name": r.name,
                "type": r.type,
                "path": rel,
                "line": r.line,
                "column": r.column,
            }
        )
    files = sorted({x["path"] for x in out if x.get("path")})
    return {
        "ok": True,
        "engine": "jedi",
        "path": path,
        "line": line,
        "column": column,
        "references": out[:200],
        "reference_count": len(out),
        "impacted_files": files,
    }


def complete(
    root: str | Path,
    path: str,
    *,
    line: int,
    column: int,
    source: str,
) -> dict[str, Any]:
    import jedi

    root_p = Path(root).resolve()
    fp = root_p / path
    script = jedi.Script(source, path=str(fp), project=_project(root_p))
    comps = script.complete(line, column)
    return {
        "ok": True,
        "engine": "jedi",
        "completions": [
            {"name": c.name, "type": c.type, "description": (c.description or "")[:120]}
            for c in comps[:40]
        ],
    }


def names_in_module(root: str | Path, path: str) -> dict[str, Any]:
    import jedi

    root_p = Path(root).resolve()
    fp = root_p / path
    code = fp.read_text(encoding="utf-8", errors="replace")
    script = jedi.Script(code, path=str(fp), project=_project(root_p))
    names = script.get_names(all_scopes=True, definitions=True)
    return {
        "ok": True,
        "engine": "jedi",
        "path": path,
        "names": [
            {
                "name": n.name,
                "type": n.type,
                "line": n.line,
                "column": n.column,
            }
            for n in names[:300]
        ],
    }


__all__ = ["goto_definition", "find_references", "complete", "names_in_module"]
