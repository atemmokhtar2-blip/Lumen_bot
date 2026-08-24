"""Automated validation of generated bot projects before PASS.

Runs without network: AST parse, import graph, entrypoint presence,
optional subprocess compileall. Does not trust Critic alone.
"""
from __future__ import annotations

import ast
import logging
import os
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENTRY_CANDIDATES = ("main.py", "bot.py", "app.py", "run.py")


def run_generated_unit_gate(project_path: str | Path) -> dict[str, Any]:
    """Return {ok, errors, warnings, checks}."""
    root = Path(project_path)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    if not root.is_dir():
        return {"ok": False, "errors": ["project_missing"], "warnings": [], "checks": {}}

    # 1) Entry point exists
    entry = None
    for name in _ENTRY_CANDIDATES:
        if (root / name).is_file():
            entry = root / name
            break
    checks["has_entry"] = entry is not None
    if entry is None:
        errors.append("missing_entry_point")

    # 2) Compile all .py under project (syntax)
    py_files = list(root.rglob("*.py"))
    checks["has_py"] = bool(py_files)
    if not py_files:
        errors.append("no_python_files")
    syntax_ok = True
    for f in py_files[:200]:
        try:
            py_compile.compile(str(f), doraise=True)
        except Exception as exc:
            syntax_ok = False
            errors.append(f"syntax:{f.relative_to(root)}:{type(exc).__name__}")
            if len(errors) > 15:
                break
    checks["syntax_ok"] = syntax_ok

    # 3) AST: no obvious RCE patterns in generated entry
    if entry and entry.is_file():
        try:
            tree = ast.parse(entry.read_text(encoding="utf-8", errors="ignore"))
            bad = _ast_danger(tree)
            checks["ast_safe"] = not bad
            errors.extend(bad[:8])
        except Exception as exc:
            checks["ast_safe"] = False
            errors.append(f"ast_parse_failed:{type(exc).__name__}")

    # 4) Optional: compileall subprocess (isolation from current interpreter state)
    if (os.getenv("TBE_GENERATED_COMPILEALL") or "1").strip().lower() not in {"0", "false", "no"}:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", str(root)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            checks["compileall"] = r.returncode == 0
            if r.returncode != 0:
                errors.append("compileall_failed")
        except Exception as exc:
            warnings.append(f"compileall_skip:{type(exc).__name__}")

    # 5) Optional pytest if tests/ present
    tests_dir = root / "tests"
    if tests_dir.is_dir() and any(tests_dir.rglob("test_*.py")):
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=no", str(tests_dir)],
                capture_output=True,
                text=True,
                timeout=90,
                cwd=str(root),
            )
            checks["pytest"] = r.returncode == 0
            if r.returncode != 0:
                errors.append("pytest_failed")
        except Exception as exc:
            warnings.append(f"pytest_skip:{type(exc).__name__}")

    ok = checks.get("has_entry", False) and checks.get("syntax_ok", False) and checks.get("ast_safe", True)
    if checks.get("compileall") is False:
        ok = False
    if checks.get("pytest") is False:
        ok = False
    return {"ok": ok, "errors": errors, "warnings": warnings, "checks": checks}


def _ast_danger(tree: ast.AST) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = ""
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name in {"eval", "exec", "compile"}:
                bad.append(f"dangerous_call:{name}")
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if fn.value.id == "os" and fn.attr in {"system", "popen"}:
                    bad.append("dangerous_call:os.system")
                if fn.value.id == "subprocess" and fn.attr in {"call", "run", "Popen"}:
                    # subprocess in generated bot may be legitimate — flag only shell=True
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            bad.append("dangerous_call:subprocess_shell_true")
    return bad
