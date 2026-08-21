"""Measurable repo tools for the engine — Grok must answer from tool outputs only."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

_SKIP = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov", "site-packages", ".eggs",
}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".cpp",
    ".h", ".cs", ".rb", ".php", ".swift", ".sh", ".sql", ".html", ".css", ".vue",
}


def _iter_files(root: Path):
    root = Path(root).resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(s in p.parts for s in _SKIP):
            continue
        yield p


def _line_count(path: Path) -> int:
    try:
        if path.stat().st_size > 3_000_000:
            return 0
        raw = path.read_bytes()
        if b"\x00" in raw[:2048]:
            return 0
        return raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    except Exception:
        return 0


def tool_stats(root: Path) -> dict[str, Any]:
    total_files = 0
    total_lines = 0
    code_lines = 0
    by_ext: Counter[str] = Counter()
    lines_by_ext: Counter[str] = Counter()
    for p in _iter_files(root):
        total_files += 1
        ext = p.suffix.lower() or "(no_ext)"
        by_ext[ext] += 1
        n = _line_count(p)
        total_lines += n
        if ext in _CODE_EXT:
            code_lines += n
            lines_by_ext[ext] += n
    return {
        "tool": "stats",
        "total_files": total_files,
        "total_lines": total_lines,
        "code_lines": code_lines,
        "files_by_extension": dict(by_ext.most_common(30)),
        "code_lines_by_extension": dict(lines_by_ext.most_common(20)),
    }


def tool_tree(root: Path, *, max_entries: int = 150, max_depth: int = 4) -> dict[str, Any]:
    root = Path(root).resolve()
    entries: list[str] = []
    for p in sorted(_iter_files(root)):
        rel = p.relative_to(root).as_posix()
        if rel.count("/") >= max_depth:
            continue
        entries.append(rel)
        if len(entries) >= max_entries:
            break
    return {"tool": "tree", "count": len(entries), "paths": entries}


def tool_largest_files(root: Path, *, limit: int = 20) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    root = Path(root).resolve()
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        rows.append({"path": rel, "lines": _line_count(p), "bytes": p.stat().st_size if p.exists() else 0})
    rows.sort(key=lambda x: x["lines"], reverse=True)
    return {"tool": "largest_files", "files": rows[:limit]}


def tool_find_files(root: Path, query: str, *, limit: int = 40) -> dict[str, Any]:
    root = Path(root).resolve()
    q = (query or "").strip().lower()
    hits: list[str] = []
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        if not q or q in rel.lower() or q in p.name.lower():
            hits.append(rel)
        if len(hits) >= limit:
            break
    return {"tool": "find_files", "query": query, "hits": hits, "count": len(hits)}


def tool_read_file(root: Path, rel_path: str, *, max_chars: int = 8000) -> dict[str, Any]:
    root = Path(root).resolve()
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return {"tool": "read_file", "ok": False, "error": "path_traversal_blocked"}
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        return {"tool": "read_file", "ok": False, "error": "not_found", "path": rel}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return {"tool": "read_file", "ok": False, "error": type(exc).__name__, "path": rel}
    return {
        "tool": "read_file",
        "ok": True,
        "path": rel,
        "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def tool_search_code(root: Path, pattern: str, *, limit: int = 30) -> dict[str, Any]:
    root = Path(root).resolve()
    pat = (pattern or "").strip()
    if not pat:
        return {"tool": "search_code", "error": "empty_pattern", "hits": []}
    try:
        rx = re.compile(pat, re.I)
    except re.error:
        rx = re.compile(re.escape(pat), re.I)
    hits: list[dict[str, Any]] = []
    for p in _iter_files(root):
        if p.suffix.lower() not in _CODE_EXT | {".md", ".txt", ".toml", ".yml", ".yaml", ".json"}:
            continue
        try:
            if p.stat().st_size > 1_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = p.relative_to(root).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                if len(hits) >= limit:
                    return {"tool": "search_code", "pattern": pat, "hits": hits, "count": len(hits)}
    return {"tool": "search_code", "pattern": pat, "hits": hits, "count": len(hits)}


def tool_dependencies(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    deps: list[str] = []
    sources: list[str] = []
    req = root / "requirements.txt"
    if req.is_file():
        sources.append("requirements.txt")
        for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                deps.append(s.split(";")[0].strip()[:80])
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        sources.append("pyproject.toml")
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"([A-Za-z0-9_.-]{2,60})(?:>=|<=|==|~=|!=)?', text):
            pkg = m.group(1)
            if pkg not in deps and pkg.lower() not in {"python", "poetry", "dependencies"}:
                deps.append(pkg)
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        sources.append("package.json")
        try:
            import json
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            for section in ("dependencies", "devDependencies"):
                for name in (data.get(section) or {}):
                    deps.append(str(name))
        except Exception:
            pass
    # uniq preserve order
    seen = set()
    uniq = []
    for d in deps:
        k = d.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return {"tool": "dependencies", "sources": sources, "packages": uniq[:80], "count": len(uniq)}


def tool_entrypoints(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    candidates = ["main.py", "bot.py", "app.py", "run.py", "server.py", "manage.py", "index.js", "src/main.py"]
    found: list[dict[str, Any]] = []
    for rel in candidates:
        p = root / rel
        if p.is_file():
            found.append({"path": rel, "lines": _line_count(p), "reason": "standard_name"})
    # package __main__
    for p in _iter_files(root):
        if p.name == "__main__.py":
            rel = p.relative_to(root).as_posix()
            found.append({"path": rel, "lines": _line_count(p), "reason": "__main__"})
        if len(found) >= 15:
            break
    return {"tool": "entrypoints", "entrypoints": found[:15]}


def tool_symbols(root: Path, rel_path: str, *, limit: int = 40) -> dict[str, Any]:
    root = Path(root).resolve()
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return {"tool": "symbols", "ok": False, "error": "path_traversal_blocked"}
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)) or not path.is_file() or path.suffix != ".py":
        return {"tool": "symbols", "ok": False, "error": "not_a_python_file", "path": rel}
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src, filename=rel)
    except Exception as exc:
        return {"tool": "symbols", "ok": False, "error": type(exc).__name__, "path": rel}
    classes: list[str] = []
    functions: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
    return {
        "tool": "symbols",
        "ok": True,
        "path": rel,
        "classes": classes[:limit],
        "functions": functions[:limit],
    }


def tool_readme(root: Path, *, max_chars: int = 6000) -> dict[str, Any]:
    root = Path(root).resolve()
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = root / name
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            return {
                "tool": "readme",
                "path": name,
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
                "lines": text.count("\n") + 1,
            }
    return {"tool": "readme", "path": None, "content": "", "truncated": False}


# Registry for engine + Grok
REPO_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "stats": lambda root, **kw: tool_stats(root),
    "tree": lambda root, **kw: tool_tree(root, max_entries=int(kw.get("max_entries") or 150)),
    "largest_files": lambda root, **kw: tool_largest_files(root, limit=int(kw.get("limit") or 20)),
    "find_files": lambda root, **kw: tool_find_files(root, str(kw.get("query") or ""), limit=int(kw.get("limit") or 40)),
    "read_file": lambda root, **kw: tool_read_file(root, str(kw.get("path") or ""), max_chars=int(kw.get("max_chars") or 8000)),
    "search_code": lambda root, **kw: tool_search_code(root, str(kw.get("pattern") or ""), limit=int(kw.get("limit") or 30)),
    "dependencies": lambda root, **kw: tool_dependencies(root),
    "entrypoints": lambda root, **kw: tool_entrypoints(root),
    "symbols": lambda root, **kw: tool_symbols(root, str(kw.get("path") or "")),
    "readme": lambda root, **kw: tool_readme(root),
}


def run_tool(name: str, root: Path, **kwargs: Any) -> dict[str, Any]:
    fn = REPO_TOOLS.get(name)
    if not fn:
        return {"tool": name, "ok": False, "error": "unknown_tool"}
    try:
        return fn(Path(root), **kwargs)
    except Exception as exc:
        return {"tool": name, "ok": False, "error": type(exc).__name__}


def run_core_toolkit(root: Path, *, user_question: str = "") -> list[dict[str, Any]]:
    """Always-on measurement pack + question-driven extra tools."""
    root = Path(root).resolve()
    out: list[dict[str, Any]] = [
        run_tool("stats", root),
        run_tool("tree", root),
        run_tool("largest_files", root),
        run_tool("dependencies", root),
        run_tool("entrypoints", root),
        run_tool("readme", root),
    ]
    q = (user_question or "").lower()
    # Heuristic extra probes from the question (still engine tools, not LLM invention)
    if any(x in q for x in ("stripe", "payment", "دفع", "سترايب")):
        out.append(run_tool("search_code", root, pattern="stripe|Stripe|STRIPE"))
    if any(x in q for x in ("api", "fastapi", "flask", "aiohttp", "مسار", "endpoint")):
        out.append(run_tool("search_code", root, pattern=r"(APIRouter|FastAPI|flask|aiohttp|@app\.|router\.)"))
        out.append(run_tool("find_files", root, query="api"))
    if any(x in q for x in ("telegram", "بوت", "bot", "handler")):
        out.append(run_tool("search_code", root, pattern=r"(telegram|Application|CommandHandler|aiogram)"))
    if any(x in q for x in ("docker", "deploy", "استضاف", "host")):
        out.append(run_tool("find_files", root, query="docker"))
        out.append(run_tool("search_code", root, pattern=r"docker|Dockerfile|hosting"))
    if any(x in q for x in ("سطر", "أسطر", "lines", "loc", "ملف")):
        # stats already included
        pass
    # Always try main entry symbols if present
    for ep in (run_tool("entrypoints", root).get("entrypoints") or [])[:3]:
        path = ep.get("path") or ""
        if path.endswith(".py"):
            out.append(run_tool("symbols", root, path=path))
    return out


def toolkit_to_prompt_block(results: list[dict[str, Any]]) -> str:
    import json
    # Compact JSON for LLM — ground truth only
    compact = []
    for r in results:
        if r.get("tool") == "readme" and r.get("content"):
            compact.append({
                "tool": "readme",
                "path": r.get("path"),
                "lines": r.get("lines"),
                "content": (r.get("content") or "")[:5000],
            })
        elif r.get("tool") == "read_file" and r.get("content"):
            compact.append({
                "tool": "read_file",
                "path": r.get("path"),
                "lines": r.get("lines"),
                "content": (r.get("content") or "")[:6000],
            })
        else:
            # drop huge content fields already handled
            c = {k: v for k, v in r.items() if k != "content"}
            compact.append(c)
    return json.dumps(compact, ensure_ascii=False, indent=0)[:24000]


__all__ = [
    "REPO_TOOLS",
    "run_tool",
    "run_core_toolkit",
    "toolkit_to_prompt_block",
    "tool_stats",
    "tool_tree",
    "tool_largest_files",
    "tool_find_files",
    "tool_read_file",
    "tool_search_code",
    "tool_dependencies",
    "tool_entrypoints",
    "tool_symbols",
    "tool_readme",
]
