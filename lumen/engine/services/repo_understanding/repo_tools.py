"""Strong measurable repo tools — Grok answers only from these outputs."""
from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

_SKIP = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov", "site-packages", ".eggs",
    ".idea", ".vscode", "coverage",
}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".sh", ".bash", ".sql", ".html",
    ".css", ".vue", ".svelte", ".mjs", ".cjs",
}
_TEXT_EXT = _CODE_EXT | {
    ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".env",
    ".example", ".rst", ".xml",
}
_SECRET_RX = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key|aws_access|ghp_|gsk_|sk_live|sk_test)"
    r"\s*[=:]\s*['\"]?([^\s'\"]{8,})"
)
_DANGEROUS_RX = re.compile(
    r"\b(eval|exec|pickle\.loads|subprocess\.(call|run|Popen)|os\.system|shell\s*=\s*True)\b"
)
_ENV_RX = re.compile(r"""(?:os\.environ(?:\.get)?|getenv)\s*\(\s*['\"]([A-Z][A-Z0-9_]{1,64})['\"]""")
_ENV_ASSIGN_RX = re.compile(r"""(?:os\.environ\s*\[\s*['\"]([A-Z][A-Z0-9_]{1,64})['\"])""")


def _iter_files(root: Path) -> Iterable[Path]:
    root = Path(root).resolve()
    for p in root.rglob("*"):
        try:
            if not p.is_file():
                continue
            if any(s in p.parts for s in _SKIP):
                continue
            yield p
        except Exception:
            continue


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def _line_count(path: Path) -> int:
    try:
        size = path.stat().st_size
        if size > 5_000_000:
            return 0
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return 0
        return raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    except Exception:
        return 0


def _read_text(path: Path, limit: int = 0) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
        return data if not limit else data[:limit]
    except Exception:
        return ""


def _safe_child(root: Path, rel_path: str) -> Optional[Path]:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    path = (root / rel).resolve()
    root_s = str(root.resolve())
    if not str(path).startswith(root_s):
        return None
    return path


def _run_git(root: Path, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as exc:
        return 1, "", type(exc).__name__


# ---------------------------------------------------------------------------
# Core tools (strengthened)
# ---------------------------------------------------------------------------

def tool_stats(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    total_files = 0
    total_lines = 0
    code_lines = 0
    blank_lines = 0
    comment_ish = 0
    by_ext: Counter[str] = Counter()
    lines_by_ext: Counter[str] = Counter()
    bytes_total = 0
    for p in _iter_files(root):
        total_files += 1
        try:
            bytes_total += p.stat().st_size
        except Exception:
            pass
        ext = p.suffix.lower() or "(no_ext)"
        by_ext[ext] += 1
        n = _line_count(p)
        total_lines += n
        if ext in _CODE_EXT:
            code_lines += n
            lines_by_ext[ext] += n
            # light blank/comment estimate for py
            if ext == ".py":
                for line in _read_text(p).splitlines():
                    s = line.strip()
                    if not s:
                        blank_lines += 1
                    elif s.startswith("#"):
                        comment_ish += 1
    return {
        "tool": "stats",
        "ok": True,
        "total_files": total_files,
        "total_lines": total_lines,
        "code_lines": code_lines,
        "approx_blank_lines_py": blank_lines,
        "approx_comment_lines_py": comment_ish,
        "total_bytes": bytes_total,
        "files_by_extension": dict(by_ext.most_common(40)),
        "code_lines_by_extension": dict(lines_by_ext.most_common(25)),
    }


def tool_tree(root: Path, *, max_entries: int = 250, max_depth: int = 5) -> dict[str, Any]:
    root = Path(root).resolve()
    dirs: Counter[str] = Counter()
    paths: list[str] = []
    for p in sorted(_iter_files(root), key=lambda x: x.as_posix()):
        rel = _rel(root, p)
        depth = rel.count("/")
        if depth >= max_depth:
            continue
        paths.append(rel)
        top = rel.split("/", 1)[0]
        dirs[top] += 1
        if len(paths) >= max_entries:
            break
    return {
        "tool": "tree",
        "ok": True,
        "count": len(paths),
        "top_level_file_counts": dict(dirs.most_common(30)),
        "paths": paths,
    }


def tool_largest_files(root: Path, *, limit: int = 30) -> dict[str, Any]:
    root = Path(root).resolve()
    rows: list[dict[str, Any]] = []
    for p in _iter_files(root):
        try:
            sz = p.stat().st_size
        except Exception:
            sz = 0
        rows.append({
            "path": _rel(root, p),
            "lines": _line_count(p),
            "bytes": sz,
            "ext": p.suffix.lower() or "(no_ext)",
        })
    by_lines = sorted(rows, key=lambda x: x["lines"], reverse=True)[:limit]
    by_bytes = sorted(rows, key=lambda x: x["bytes"], reverse=True)[: min(15, limit)]
    return {
        "tool": "largest_files",
        "ok": True,
        "by_lines": by_lines,
        "by_bytes": by_bytes,
        # compat
        "files": by_lines,
    }


def tool_find_files(root: Path, query: str, *, limit: int = 60) -> dict[str, Any]:
    root = Path(root).resolve()
    q = (query or "").strip().lower()
    hits: list[dict[str, Any]] = []
    for p in _iter_files(root):
        rel = _rel(root, p)
        name = p.name.lower()
        if not q or q in rel.lower() or q in name or (q.startswith("*.") and name.endswith(q[1:])):
            hits.append({"path": rel, "lines": _line_count(p), "ext": p.suffix.lower() or "(no_ext)"})
        if len(hits) >= limit:
            break
    return {"tool": "find_files", "ok": True, "query": query, "count": len(hits), "hits": hits}


def tool_read_file(root: Path, rel_path: str, *, max_chars: int = 12000) -> dict[str, Any]:
    root = Path(root).resolve()
    path = _safe_child(root, rel_path)
    if path is None:
        return {"tool": "read_file", "ok": False, "error": "path_blocked", "path": rel_path}
    if not path.is_file():
        return {"tool": "read_file", "ok": False, "error": "not_found", "path": rel_path}
    text = _read_text(path)
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return {
        "tool": "read_file",
        "ok": True,
        "path": _rel(root, path),
        "lines": lines,
        "bytes": path.stat().st_size,
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
        "sha1_prefix": __import__("hashlib").sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12],
    }


def tool_search_code(root: Path, pattern: str, *, limit: int = 40) -> dict[str, Any]:
    root = Path(root).resolve()
    pat = (pattern or "").strip()
    if not pat:
        return {"tool": "search_code", "ok": False, "error": "empty_pattern", "hits": []}
    try:
        rx = re.compile(pat, re.I)
    except re.error:
        rx = re.compile(re.escape(pat), re.I)
    hits: list[dict[str, Any]] = []
    files_scanned = 0
    for p in _iter_files(root):
        if p.suffix.lower() not in _TEXT_EXT:
            continue
        try:
            if p.stat().st_size > 1_500_000:
                continue
        except Exception:
            continue
        text = _read_text(p)
        if not text:
            continue
        files_scanned += 1
        rel = _rel(root, p)
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"path": rel, "line": i, "text": line.strip()[:240]})
                if len(hits) >= limit:
                    return {
                        "tool": "search_code",
                        "ok": True,
                        "pattern": pat,
                        "hits": hits,
                        "count": len(hits),
                        "files_scanned": files_scanned,
                        "capped": True,
                    }
    return {
        "tool": "search_code",
        "ok": True,
        "pattern": pat,
        "hits": hits,
        "count": len(hits),
        "files_scanned": files_scanned,
        "capped": False,
    }


def tool_dependencies(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    deps: list[str] = []
    sources: list[str] = []
    sections: dict[str, list[str]] = {}

    req = root / "requirements.txt"
    if req.is_file():
        sources.append("requirements.txt")
        rows = []
        for line in _read_text(req).splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("-"):
                rows.append(s.split(";")[0].strip()[:100])
        sections["requirements.txt"] = rows
        deps.extend(rows)

    for fname in ("requirements-dev.txt", "requirements.prod.txt"):
        p = root / fname
        if p.is_file():
            sources.append(fname)
            rows = [ln.strip() for ln in _read_text(p).splitlines() if ln.strip() and not ln.strip().startswith("#")]
            sections[fname] = rows[:50]
            deps.extend(rows)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        sources.append("pyproject.toml")
        text = _read_text(pyproject)
        rows = []
        for m in re.finditer(r'^\s*["\']([A-Za-z0-9_.-]{2,80})["\']\s*[=~<>!]', text, re.M):
            rows.append(m.group(1))
        # poetry style
        for m in re.finditer(r'^\s*([A-Za-z0-9_.-]{2,80})\s*=\s*["\']', text, re.M):
            name = m.group(1)
            if name.lower() not in {"python", "version", "description", "name", "authors"}:
                rows.append(name)
        sections["pyproject.toml"] = list(dict.fromkeys(rows))[:80]
        deps.extend(sections["pyproject.toml"])

    pkg = root / "package.json"
    if pkg.is_file():
        sources.append("package.json")
        try:
            data = json.loads(_read_text(pkg) or "{}")
            rows = []
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, ver in (data.get(section) or {}).items():
                    rows.append(f"{name}@{ver}")
            sections["package.json"] = rows[:80]
            deps.extend([r.split("@")[0] for r in rows])
        except Exception:
            pass

    uniq = list(dict.fromkeys(deps))
    return {
        "tool": "dependencies",
        "ok": True,
        "sources": sources,
        "packages": uniq[:120],
        "count": len(uniq),
        "by_source": sections,
    }


def tool_entrypoints(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    found: list[dict[str, Any]] = []
    standard = [
        "main.py", "bot.py", "app.py", "run.py", "server.py", "manage.py",
        "wsgi.py", "asgi.py", "index.js", "src/main.py", "src/index.js",
        "lumen.engine/__main__.py",
    ]
    for rel in standard:
        p = root / rel
        if p.is_file():
            found.append({"path": rel, "lines": _line_count(p), "reason": "standard_name"})
    for p in _iter_files(root):
        if p.name == "__main__.py":
            found.append({"path": _rel(root, p), "lines": _line_count(p), "reason": "__main__"})
        # if __name__ == '__main__'
        if p.suffix == ".py" and p.stat().st_size < 400_000:
            text = _read_text(p, 50_000)
            if re.search(r"""if\s+__name__\s*==\s*['\"]__main__['\"]""", text):
                rel = _rel(root, p)
                if not any(x["path"] == rel for x in found):
                    found.append({"path": rel, "lines": _line_count(p), "reason": "name_main_guard"})
        if len(found) >= 25:
            break
    return {"tool": "entrypoints", "ok": True, "entrypoints": found[:25], "count": len(found[:25])}


def tool_symbols(root: Path, rel_path: str, *, limit: int = 60) -> dict[str, Any]:
    root = Path(root).resolve()
    path = _safe_child(root, rel_path)
    if path is None or not path.is_file():
        return {"tool": "symbols", "ok": False, "error": "not_found", "path": rel_path}
    if path.suffix != ".py":
        return {"tool": "symbols", "ok": False, "error": "not_python", "path": rel_path}
    src = _read_text(path)
    try:
        tree = ast.parse(src, filename=str(path))
    except Exception as exc:
        return {"tool": "symbols", "ok": False, "error": type(exc).__name__, "path": rel_path}
    classes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({"name": node.name, "lineno": node.lineno, "methods": methods[:20]})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "lineno": node.lineno,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "args": [a.arg for a in node.args.args][:12],
            })
        elif isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append(mod)
    return {
        "tool": "symbols",
        "ok": True,
        "path": _rel(root, path),
        "classes": classes[:limit],
        "functions": functions[:limit],
        "imports_top": list(dict.fromkeys(imports))[:40],
        "class_count": len(classes),
        "function_count": len(functions),
    }


def tool_readme(root: Path, *, max_chars: int = 8000) -> dict[str, Any]:
    root = Path(root).resolve()
    for name in ("README.md", "README.rst", "README.txt", "README", "docs/README.md"):
        p = root / name
        if p.is_file():
            text = _read_text(p)
            return {
                "tool": "readme",
                "ok": True,
                "path": name,
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
                "lines": text.count("\n") + 1,
            }
    return {"tool": "readme", "ok": False, "path": None, "content": "", "truncated": False}


# ---------------------------------------------------------------------------
# Six additional strong tools
# ---------------------------------------------------------------------------

def tool_git_log(root: Path, *, limit: int = 15) -> dict[str, Any]:
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return {"tool": "git_log", "ok": False, "error": "not_a_git_repo"}
    code, out, err = _run_git(
        root,
        ["log", f"-{int(limit)}", "--format=%H|%an|%ae|%ad|%s", "--date=short"],
        timeout=25,
    )
    if code != 0:
        return {"tool": "git_log", "ok": False, "error": (err or out)[:300]}
    commits = []
    for line in out.splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0][:12],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "subject": parts[4][:160],
            })
    # branch + head
    _, branch, _ = _run_git(root, ["branch", "--show-current"], timeout=10)
    _, head, _ = _run_git(root, ["rev-parse", "--short", "HEAD"], timeout=10)
    return {
        "tool": "git_log",
        "ok": True,
        "branch": branch.strip(),
        "head": head.strip(),
        "commits": commits,
        "count": len(commits),
    }


def tool_git_blame(root: Path, rel_path: str, *, max_lines: int = 40) -> dict[str, Any]:
    root = Path(root).resolve()
    path = _safe_child(root, rel_path)
    if path is None or not path.is_file():
        return {"tool": "git_blame", "ok": False, "error": "not_found", "path": rel_path}
    if not (root / ".git").exists():
        return {"tool": "git_blame", "ok": False, "error": "not_a_git_repo"}
    code, out, err = _run_git(
        root,
        ["blame", "-e", "--line-porcelain", str(path.relative_to(root))],
        timeout=40,
    )
    if code != 0:
        # fallback simpler blame
        code2, out2, err2 = _run_git(root, ["blame", "-e", str(path.relative_to(root))], timeout=30)
        if code2 != 0:
            return {"tool": "git_blame", "ok": False, "error": (err or err2 or out)[:300], "path": rel_path}
        lines = []
        for i, line in enumerate(out2.splitlines()[:max_lines], 1):
            lines.append({"line": i, "raw": line[:200]})
        return {"tool": "git_blame", "ok": True, "path": rel_path, "mode": "simple", "lines": lines}

    authors: Counter[str] = Counter()
    entries: list[dict[str, Any]] = []
    cur_author = ""
    cur_summary = ""
    line_no = 0
    for line in out.splitlines():
        if line.startswith("author "):
            cur_author = line[7:].strip()
        elif line.startswith("summary "):
            cur_summary = line[8:].strip()[:80]
        elif line.startswith("\t"):
            line_no += 1
            authors[cur_author or "?"] += 1
            if len(entries) < max_lines:
                entries.append({
                    "line": line_no,
                    "author": cur_author,
                    "summary": cur_summary,
                    "text": line[1:160],
                })
    return {
        "tool": "git_blame",
        "ok": True,
        "path": rel_path,
        "author_line_counts": dict(authors.most_common(15)),
        "sample": entries,
    }


def tool_import_graph(root: Path, *, limit_modules: int = 80, limit_edges: int = 200) -> dict[str, Any]:
    root = Path(root).resolve()
    edges: list[dict[str, str]] = []
    internal_mods: set[str] = set()
    external: Counter[str] = Counter()
    py_files = [p for p in _iter_files(root) if p.suffix == ".py"]
    # module name map
    for p in py_files:
        rel = _rel(root, p)
        mod = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        internal_mods.add(mod)

    for p in py_files[:400]:
        rel = _rel(root, p)
        src_mod = rel[:-3].replace("/", ".")
        if src_mod.endswith(".__init__"):
            src_mod = src_mod[: -len(".__init__")]
        try:
            tree = ast.parse(_read_text(p, 200_000), filename=rel)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = (a.name or "").split(".")[0]
                    if any(m == a.name or m.startswith(a.name + ".") for m in internal_mods):
                        edges.append({"from": src_mod, "to": a.name, "kind": "import"})
                    else:
                        external[top] += 1
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0] if mod else ""
                if mod and any(m == mod or m.startswith(mod + ".") or mod.startswith(m + ".") for m in list(internal_mods)[:500]):
                    edges.append({"from": src_mod, "to": mod, "kind": "from"})
                elif top:
                    external[top] += 1
            if len(edges) >= limit_edges:
                break
        if len(edges) >= limit_edges:
            break

    return {
        "tool": "import_graph",
        "ok": True,
        "internal_edge_count": len(edges),
        "internal_edges_sample": edges[:limit_edges],
        "external_packages_top": dict(external.most_common(40)),
        "modules_indexed": min(len(py_files), 400),
    }


def tool_test_discovery(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    tests: list[dict[str, Any]] = []
    test_funcs = 0
    for p in _iter_files(root):
        name = p.name
        rel = _rel(root, p)
        is_test_path = (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "/tests/" in f"/{rel}/"
            or "/test/" in f"/{rel}/"
        )
        if not is_test_path:
            continue
        if p.suffix != ".py":
            tests.append({"path": rel, "kind": "non_py"})
            continue
        text = _read_text(p, 200_000)
        funcs = re.findall(r"^\s*def\s+(test_\w+)", text, re.M)
        classes = re.findall(r"^\s*class\s+(Test\w+)", text, re.M)
        test_funcs += len(funcs)
        tests.append({
            "path": rel,
            "kind": "py",
            "test_functions": funcs[:30],
            "test_classes": classes[:20],
            "test_function_count": len(funcs),
            "lines": _line_count(p),
        })
        if len(tests) >= 80:
            break
    return {
        "tool": "test_discovery",
        "ok": True,
        "test_files": len(tests),
        "test_functions_total": test_funcs,
        "tests": tests[:80],
        "has_tests": len(tests) > 0,
    }


def tool_config_scan(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    env_vars: Counter[str] = Counter()
    config_files: list[str] = []
    for p in _iter_files(root):
        rel = _rel(root, p)
        low = rel.lower()
        if any(x in low for x in (".env", "config", "settings", "pyproject.toml", "docker-compose", "procfile")):
            if p.suffix.lower() in _TEXT_EXT or p.name.lower() in {".env", ".env.example", "procfile"}:
                config_files.append(rel)
        if p.suffix == ".py":
            text = _read_text(p, 150_000)
            for m in _ENV_RX.finditer(text):
                env_vars[m.group(1)] += 1
            for m in _ENV_ASSIGN_RX.finditer(text):
                env_vars[m.group(1)] += 1
    # .env.example keys
    example_keys: list[str] = []
    for name in (".env.example", ".env.sample", "env.example"):
        p = root / name
        if p.is_file():
            for line in _read_text(p).splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    example_keys.append(line.split("=", 1)[0].strip())
    return {
        "tool": "config_scan",
        "ok": True,
        "env_vars_used_in_code": dict(env_vars.most_common(60)),
        "env_var_count": len(env_vars),
        "env_example_keys": example_keys[:60],
        "config_files": sorted(set(config_files))[:40],
    }


def tool_security_scan(root: Path, *, limit: int = 40) -> dict[str, Any]:
    root = Path(root).resolve()
    secrets: list[dict[str, Any]] = []
    dangerous: list[dict[str, Any]] = []
    for p in _iter_files(root):
        if p.suffix.lower() not in _TEXT_EXT and p.name.lower() not in {".env", ".env.example"}:
            continue
        try:
            if p.stat().st_size > 1_000_000:
                continue
        except Exception:
            continue
        rel = _rel(root, p)
        # skip obvious false-positive docs heavily? still scan
        for i, line in enumerate(_read_text(p).splitlines(), 1):
            if _SECRET_RX.search(line) and "example" not in line.lower():
                # redact value
                red = _SECRET_RX.sub(r"\1=***REDACTED***", line.strip())
                secrets.append({"path": rel, "line": i, "text": red[:200]})
            if p.suffix == ".py" and _DANGEROUS_RX.search(line):
                dangerous.append({"path": rel, "line": i, "text": line.strip()[:200]})
            if len(secrets) >= limit and len(dangerous) >= limit:
                break
        if len(secrets) >= limit and len(dangerous) >= limit:
            break
    return {
        "tool": "security_scan",
        "ok": True,
        "possible_secrets": secrets[:limit],
        "dangerous_calls": dangerous[:limit],
        "secret_hit_count": len(secrets),
        "dangerous_hit_count": len(dangerous),
    }


def tool_diff_since(root: Path, since: str = "HEAD~10") -> dict[str, Any]:
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return {"tool": "diff_since", "ok": False, "error": "not_a_git_repo"}
    rev = (since or "HEAD~10").strip() or "HEAD~10"
    # validate-ish
    if not re.match(r"^[\w~./^-]+$", rev):
        return {"tool": "diff_since", "ok": False, "error": "invalid_rev"}
    code, out, err = _run_git(root, ["diff", "--stat", rev, "HEAD"], timeout=40)
    if code != 0:
        # try log if shallow
        code2, out2, err2 = _run_git(root, ["log", "--oneline", rev + "..HEAD"], timeout=30)
        return {
            "tool": "diff_since",
            "ok": code2 == 0,
            "since": rev,
            "error": (err or err2)[:300] if code2 != 0 else "",
            "log": out2.splitlines()[:40],
        }
    code_n, out_n, _ = _run_git(root, ["diff", "--numstat", rev, "HEAD"], timeout=40)
    files = []
    if code_n == 0:
        for line in out_n.splitlines()[:50]:
            parts = line.split("\t")
            if len(parts) >= 3:
                files.append({"added": parts[0], "deleted": parts[1], "path": parts[2]})
    return {
        "tool": "diff_since",
        "ok": True,
        "since": rev,
        "stat": out[:2500],
        "files": files,
        "file_count": len(files),
    }


# ---------------------------------------------------------------------------
# Registry + orchestration
# ---------------------------------------------------------------------------



def tool_git_push(root: Path, *, token: str = "", message: str = "") -> dict[str, Any]:
    """Push active repo via smart_git engine (not simulation)."""
    root = Path(root).resolve()
    try:
        from lumen.engine.services.git_safe_import import get_smart_git
        sg = get_smart_git()
        res = sg.git_push(str(root), token=token or None, message=message or None)
        ok = bool(getattr(res, "ok", False) if not isinstance(res, dict) else res.get("ok"))
        msg = getattr(res, "message", None) if not isinstance(res, dict) else res.get("message")
        return {
            "tool": "git_push",
            "ok": ok,
            "message": str(msg or ("pushed" if ok else "push_failed")),
            "path": str(root),
        }
    except Exception as exc:
        return {"tool": "git_push", "ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}


def tool_git_pull(root: Path, *, token: str = "") -> dict[str, Any]:
    """Pull latest for active repo via smart_git engine."""
    root = Path(root).resolve()
    try:
        from lumen.engine.services.git_safe_import import get_smart_git
        sg = get_smart_git()
        res = sg.git_pull(str(root), token=token or None)
        ok = bool(getattr(res, "ok", False) if not isinstance(res, dict) else res.get("ok"))
        msg = getattr(res, "message", None) if not isinstance(res, dict) else res.get("message")
        return {
            "tool": "git_pull",
            "ok": ok,
            "message": str(msg or ("pulled" if ok else "pull_failed")),
            "path": str(root),
        }
    except Exception as exc:
        return {"tool": "git_pull", "ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}


REPO_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "stats": lambda root, **kw: tool_stats(root),
    "tree": lambda root, **kw: tool_tree(root, max_entries=int(kw.get("max_entries") or 250)),
    "largest_files": lambda root, **kw: tool_largest_files(root, limit=int(kw.get("limit") or 30)),
    "find_files": lambda root, **kw: tool_find_files(root, str(kw.get("query") or ""), limit=int(kw.get("limit") or 60)),
    "read_file": lambda root, **kw: tool_read_file(root, str(kw.get("path") or ""), max_chars=int(kw.get("max_chars") or 12000)),
    "search_code": lambda root, **kw: tool_search_code(root, str(kw.get("pattern") or ""), limit=int(kw.get("limit") or 40)),
    "dependencies": lambda root, **kw: tool_dependencies(root),
    "entrypoints": lambda root, **kw: tool_entrypoints(root),
    "symbols": lambda root, **kw: tool_symbols(root, str(kw.get("path") or "")),
    "readme": lambda root, **kw: tool_readme(root),
    # new six
    "git_log": lambda root, **kw: tool_git_log(root, limit=int(kw.get("limit") or 15)),
    "git_blame": lambda root, **kw: tool_git_blame(root, str(kw.get("path") or "")),
    "import_graph": lambda root, **kw: tool_import_graph(root),
    "test_discovery": lambda root, **kw: tool_test_discovery(root),
    "config_scan": lambda root, **kw: tool_config_scan(root),
    "security_scan": lambda root, **kw: tool_security_scan(root),
    "diff_since": lambda root, **kw: tool_diff_since(root, str(kw.get("since") or "HEAD~10")),
    "git_push": lambda root, **kw: tool_git_push(root, token=str(kw.get("token") or ""), message=str(kw.get("message") or "")),
    "git_pull": lambda root, **kw: tool_git_pull(root, token=str(kw.get("token") or "")),
}


def run_tool(name: str, root: Path, **kwargs: Any) -> dict[str, Any]:
    fn = REPO_TOOLS.get(name)
    if not fn:
        return {"tool": name, "ok": False, "error": "unknown_tool"}
    try:
        return fn(Path(root), **kwargs)
    except Exception as exc:
        return {"tool": name, "ok": False, "error": type(exc).__name__}


_FILE_NAME_RX = re.compile(
    r"""(?ix)
    (?:
        [\w./\-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|kt|c|cpp|h|hpp|cs|rb|php|swift|
        sh|bash|sql|html|css|vue|svelte|md|txt|toml|ya?ml|json|ini|cfg|env|rst|xml|Dockerfile)
    )
    |
    (?:(?:file|path|ملف|مسار)\s*[:\-]?\s*)([\w./\-]+\.[\w]+)
    """
)

_FILE_REQUEST_HINTS = (
    "هات", "جيب", "اعرض", "وريني", "ورني", "افتح", "اقرأ", "اقرا", "محتوى",
    "show", "read", "open", "get", "file", "content", "contents", "ملف",
)


def extract_file_queries(user_question: str) -> list[str]:
    """Pull likely file names/paths from free-form user text."""
    text = user_question or ""
    found: list[str] = []
    for m in _FILE_NAME_RX.finditer(text):
        s = (m.group(0) or "").strip()
        # strip leading arabic/english keywords if captured as whole
        s = re.sub(
            r"^(?:file|path|ملف|مسار)\s*[:\-]?\s*",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip()
        if s and s not in found:
            found.append(s)
    # bare basename after "هات/جيب/..." e.g. هات main.py or هات requirements
    low = text.lower()
    if any(h in low or h in text for h in _FILE_REQUEST_HINTS):
        for tok in re.findall(r"[\w.\-/]+", text):
            if "." in tok and tok not in found and len(tok) < 120:
                found.append(tok)
            elif tok.lower() in {
                "readme", "dockerfile", "makefile", "requirements", "pyproject",
                "package", "main", "app", "config", "settings",
            } and tok not in found:
                found.append(tok)
    return found[:12]


def run_core_toolkit(root: Path, *, user_question: str = "") -> list[dict[str, Any]]:
    """Run measurable tools; always bias toward the user's free-form question.

    For questions like «هات الملف X» or any unexpected ask, Grok only answers
    from these tool outputs — so we must actually *run* find/read/search when
    the question points at files or terms.
    """
    root = Path(root).resolve()
    q = (user_question or "").lower()
    out: list[dict[str, Any]] = [
        run_tool("stats", root),
        run_tool("tree", root),
        run_tool("largest_files", root),
        run_tool("dependencies", root),
        run_tool("entrypoints", root),
        run_tool("readme", root),
        run_tool("test_discovery", root),
        run_tool("config_scan", root),
        run_tool("import_graph", root),
        run_tool("git_log", root),
    ]

    # --- File-oriented free-form requests (هات الملف / read X / show main.py) ---
    file_queries = extract_file_queries(user_question or "")
    file_request = bool(file_queries) or any(h in q or h in (user_question or "") for h in _FILE_REQUEST_HINTS)
    if file_request or file_queries:
        for fq in file_queries or ["readme", "main", "requirements"]:
            hits = run_tool("find_files", root, query=fq, limit=20)
            out.append(hits)
            for hit in (hits.get("hits") or [])[:3]:
                rel = str(hit.get("path") or "")
                if rel:
                    out.append(run_tool("read_file", root, path=rel, max_chars=14000))
        # If user named an exact relative path, try read directly
        for fq in file_queries:
            if "/" in fq or fq.endswith((".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt")):
                out.append(run_tool("read_file", root, path=fq, max_chars=14000))

    # --- Generic search terms from the question (unexpected questions) ---
    # Extract meaningful tokens (len>=3) not stopwords; search code for them.
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "what", "how", "هل",
        "ايه", "فين", "عايز", "ممكن", "لو", "عن", "في", "من", "على", "هو", "هي",
        "file", "path", "repo", "مستودع", "مشروع", "كود", "code", "please",
    }
    tokens = [
        t for t in re.findall(r"[A-Za-z_][\w]{2,}|[\u0600-\u06FF]{3,}", user_question or "")
        if t.lower() not in stop and t not in stop
    ][:8]
    if tokens and not file_request:
        # Prefer search_code on distinctive tokens
        for tok in tokens[:4]:
            if re.match(r"^[A-Za-z_]", tok):
                out.append(run_tool("search_code", root, pattern=re.escape(tok), limit=25))
                out.append(run_tool("find_files", root, query=tok, limit=15))

    # question-driven domain hooks
    if any(x in q for x in ("stripe", "payment", "دفع", "سترايب", "billing")):
        out.append(run_tool("search_code", root, pattern=r"stripe|Stripe|STRIPE"))
    if any(x in q for x in ("api", "fastapi", "flask", "aiohttp", "endpoint", "مسار")):
        out.append(run_tool("search_code", root, pattern=r"(APIRouter|FastAPI|flask|aiohttp|@app\.|router\.)"))
        out.append(run_tool("find_files", root, query="api"))
    if any(x in q for x in ("telegram", "بوت", "bot", "handler")):
        out.append(run_tool("search_code", root, pattern=r"(telegram|Application|CommandHandler|aiogram)"))
    if any(x in q for x in ("docker", "deploy", "استضاف", "host", "أمن", "security", "سر", "secret", "token")):
        out.append(run_tool("security_scan", root)
        )
        out.append(run_tool("find_files", root, query="docker"))
    if any(x in q for x in ("blame", "مين كتب", "من كتب", "author", "مؤلف")):
        eps = run_tool("entrypoints", root).get("entrypoints") or []
        if eps:
            out.append(run_tool("git_blame", root, path=eps[0].get("path") or "main.py"))
    if any(x in q for x in ("diff", "تغيّر", "تغير", "commits", "آخر", "اخر")):
        out.append(run_tool("diff_since", root, since="HEAD~15"))
    if any(x in q for x in ("test", "اختبار", "pytest")):
        out.append(run_tool("find_files", root, query="test_"))
    # symbols for top entrypoints
    for ep in (run_tool("entrypoints", root).get("entrypoints") or [])[:3]:
        path = ep.get("path") or ""
        if str(path).endswith(".py"):
            out.append(run_tool("symbols", root, path=path))
    if not any(r.get("tool") == "security_scan" for r in out):
        out.append(run_tool("security_scan", root))
    return out


def toolkit_to_prompt_block(results: list[dict[str, Any]]) -> str:
    compact = []
    for r in results:
        if r.get("tool") in {"readme", "read_file"} and r.get("content"):
            compact.append({
                "tool": r.get("tool"),
                "path": r.get("path"),
                "lines": r.get("lines"),
                "ok": r.get("ok", True),
                "content": (r.get("content") or "")[:6000],
                "truncated": r.get("truncated"),
            })
        else:
            c = {k: v for k, v in r.items() if k != "content"}
            compact.append(c)
    # Prefer large window so Grok (big-context models) can see file contents
    try:
        import os as _os
        cap = max(20000, int(_os.getenv("REPO_TOOLKIT_PROMPT_CHARS") or "52000"))
    except Exception:
        cap = 52000
    return json.dumps(compact, ensure_ascii=False, indent=0)[:cap]


__all__ = [
    "extract_file_queries",
    "REPO_TOOLS",
    "run_tool",
    "run_core_toolkit",
    "toolkit_to_prompt_block",
]
