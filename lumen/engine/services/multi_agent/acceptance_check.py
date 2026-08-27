"""Professional acceptance evaluation for generated projects.

Uses the standard library (ast, py_compile, compileall) — no mock heuristics as pass.
Unknown criteria → fail (not soft-pass) when mode is strict (default).
"""
from __future__ import annotations

import ast
import logging
import py_compile
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _read(root: Path, rel: str) -> str:
    p = root / rel
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _py_files(root: Path, files: list[str] | None) -> list[Path]:
    out: list[Path] = []
    if files:
        for f in files:
            p = root / f
            if p.is_file() and p.suffix == ".py":
                out.append(p)
    if not out:
        for p in root.rglob("*.py"):
            if any(x in p.parts for x in (".git", "__pycache__", ".venv", "venv")):
                continue
            out.append(p)
            if len(out) >= 50:
                break
    return out


def parse_python(path: Path) -> tuple[ast.AST | None, str | None]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(src, filename=str(path)), None
    except SyntaxError as exc:
        return None, f"{exc.msg} line {exc.lineno}"
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"


def check_files_exist(root: Path, files: list[str]) -> list[dict[str, Any]]:
    rows = []
    for f in files or []:
        ok = (root / f).is_file()
        rows.append({"id": f"file:{f}", "ok": ok, "detail": "exists" if ok else "missing"})
    return rows


def check_syntax_ast(root: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    rows = []
    for p in _py_files(root, files):
        tree, err = parse_python(p)
        rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
        if tree is None:
            rows.append({"id": f"syntax:{rel}", "ok": False, "detail": err or "parse_failed"})
        else:
            # also py_compile for bytecode edge cases
            try:
                py_compile.compile(str(p), doraise=True)
                rows.append({"id": f"syntax:{rel}", "ok": True, "detail": "ast+compile"})
            except Exception as exc:
                rows.append({"id": f"syntax:{rel}", "ok": False, "detail": str(exc)[:240]})
    if not rows:
        rows.append({"id": "syntax:none", "ok": False, "detail": "no_python_files"})
    return rows


def _ast_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def _main_ast(root: Path) -> tuple[ast.AST | None, str]:
    main = root / "main.py"
    if not main.is_file():
        return None, ""
    tree, _ = parse_python(main)
    src = _read(root, "main.py")
    return tree, src


def check_criterion(root: Path, criterion: str, *, strict: bool = True) -> dict[str, Any]:
    c_raw = (criterion or "").strip()
    c = c_raw.lower()
    if not c:
        return {"id": "empty", "ok": True, "detail": "empty_criterion"}

    # --- file exists ---
    m = re.search(r"([a-zA-Z0-9_./-]+\.py)\s+exists", c)
    if m:
        ok = (root / m.group(1)).is_file()
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "file_exists" if ok else "file_missing"}

    if "compileall" in c or "compiles" in c or "syntax" in c or "valid python" in c:
        rows = check_syntax_ast(root)
        ok = all(r["ok"] for r in rows)
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "syntax_all" if ok else "syntax_fail"}

    if "importable" in c or "import" in c and "main" in c:
        tree, src = _main_ast(root)
        ok = tree is not None
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "main_ast" if ok else "main_unparseable"}

    if "requirements" in c:
        req = _read(root, "requirements.txt").lower()
        if "telegram" in c:
            ok = any(x in req for x in ("python-telegram-bot", "aiogram", "pyrogram", "telebot"))
            return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "req_telegram"}
        if "discord" in c:
            ok = "discord" in req
            return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "req_discord"}
        ok = (root / "requirements.txt").is_file() and len(req.strip()) > 0
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "req_present"}

    if "token" in c and ("env" in c or "environment" in c):
        tree, src = _main_ast(root)
        ok = bool(re.search(r"getenv|environ\[|environ\.get", src))
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "env_token"}

    if "/start" in c or "start handler" in c:
        tree, src = _main_ast(root)
        names = _ast_names(tree) if tree else set()
        ok = (
            ("start" in names or "CommandHandler" in names or "command" in src.lower())
            and ("start" in src.lower())
        )
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "start_handler"}

    if "fallback" in c or "unknown" in c:
        tree, src = _main_ast(root)
        ok = bool(re.search(r"MessageHandler|fallback|UNKNOWN|else\s*:", src, re.I))
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "fallback"}

    if "discord" in c and ("client" in c or "bot" in c or "setup" in c):
        tree, src = _main_ast(root)
        ok = bool(re.search(r"discord|commands\.Bot|Client\(", src, re.I))
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "discord_client"}

    if "health" in c or "route" in c:
        tree, src = _main_ast(root)
        ok = bool(re.search(r"FastAPI|Flask|@app\.|APIRouter|/health|route\(", src))
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "web_route"}

    if "logging" in c:
        tree, src = _main_ast(root)
        ok = "logging" in src or "logger" in src.lower()
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "logging"}

    if "handler" in c or "feature" in c or "working" in c or "wired" in c:
        # require main has non-trivial defs
        tree, src = _main_ast(root)
        if tree is None:
            return {"id": f"crit:{c_raw[:40]}", "ok": False, "detail": "no_main"}
        defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        ok = len(defs) >= 2
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": f"handlers={len(defs)}"}

    if "readme" in c:
        ok = (root / "README.md").is_file()
        return {"id": f"crit:{c_raw[:40]}", "ok": ok, "detail": "readme"}

    # Strict: unknown criterion fails (professional, not soft-pass)
    if strict:
        # If main exists and parses, still fail unknown to force explicit criteria design
        return {"id": f"crit:{c_raw[:40]}", "ok": False, "detail": "unknown_criterion_fail_closed"}
    tree, _ = _main_ast(root)
    return {"id": f"crit:{c_raw[:40]}", "ok": tree is not None, "detail": "unknown_soft", "soft": True}


def evaluate_task(
    root: Path | str,
    *,
    files: list[str] | None = None,
    acceptance: list[str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    files = list(files or [])
    acceptance = list(acceptance or [])
    checks: list[dict[str, Any]] = []
    checks.extend(check_files_exist(root, files))
    checks.extend(check_syntax_ast(root, files or None))
    for a in acceptance:
        checks.append(check_criterion(root, a, strict=strict))
    # If no acceptance and no files — require main.py syntax at minimum
    if not acceptance and not files:
        checks.extend(check_syntax_ast(root, ["main.py"] if (root / "main.py").is_file() else None))
    failed = [c for c in checks if not c.get("ok")]
    return {
        "ok": len(failed) == 0 and len(checks) > 0,
        "checks": checks,
        "failed": failed,
        "failed_count": len(failed),
        "engine": "acceptance_ast_v2",
        "strict": strict,
    }


def evaluate_tree(root: Path | str, tree: Any, *, strict: bool = True) -> dict[str, Any]:
    root = Path(root)
    task_results: dict[str, Any] = {}
    all_ok = True
    nodes = getattr(tree, "nodes", {}) or {}
    root_id = getattr(tree, "root_id", None)
    for node in nodes.values():
        nid = getattr(node, "id", "")
        if nid in {root_id, "root", ""}:
            continue
        status = str(getattr(node, "status", "")).lower()
        if status not in {"done", "completed", "failed"}:
            continue
        r = evaluate_task(
            root,
            files=list(getattr(node, "files", None) or []),
            acceptance=list(getattr(node, "acceptance", None) or []),
            strict=strict,
        )
        task_results[nid] = r
        if status == "done" and not r.get("ok"):
            all_ok = False
    if not task_results:
        # whole project fallback
        r = evaluate_task(root, files=["main.py"], acceptance=["main.py exists", "compileall passes"], strict=strict)
        task_results["_project"] = r
        all_ok = bool(r.get("ok"))
    return {"ok": all_ok, "tasks": task_results, "engine": "acceptance_tree_v2", "strict": strict}


__all__ = [
    "parse_python",
    "check_files_exist",
    "check_syntax_ast",
    "check_criterion",
    "evaluate_task",
    "evaluate_tree",
]
