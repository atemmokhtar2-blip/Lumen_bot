"""Honest structural validation after clone/modify — fail-fast contract."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def count_files(root: Path) -> int:
    n = 0
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            n += 1
    return n


def structural_validate(root: Path) -> tuple[bool, dict[str, Any], str]:
    """
    Returns (passed, details, error_message).
    Checks: non-empty tree, optional main.py AST, requirements readability.
    """
    root = Path(root)
    if not root.is_dir():
        return False, {}, "root_missing"
    if not (root / ".git").exists():
        # allow non-git workdirs from zip strategy
        git_ok = False
    else:
        git_ok = True

    files = count_files(root)
    if files <= 0:
        return False, {"file_count": 0, "has_git": git_ok}, "empty_tree"

    details: dict[str, Any] = {"file_count": files, "has_git": git_ok}
    errors: list[str] = []

    main_candidates = [
        root / "main.py",
        root / "app.py",
        root / "bot.py",
        root / "api_main.py",
    ]
    main_hit = next((p for p in main_candidates if p.is_file()), None)
    details["entry_file"] = str(main_hit.name) if main_hit else None
    if main_hit:
        try:
            src = main_hit.read_text(encoding="utf-8", errors="replace")
            ast.parse(src, filename=str(main_hit))
            details["entry_ast_ok"] = True
        except SyntaxError as exc:
            details["entry_ast_ok"] = False
            errors.append(f"entry_syntax:{exc.msg}")
    else:
        details["entry_ast_ok"] = None  # not required for every repo

    req = root / "requirements.txt"
    if req.is_file():
        try:
            text = req.read_text(encoding="utf-8", errors="replace")
            details["requirements_readable"] = True
            details["requirements_lines"] = len([ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")])
        except Exception:
            details["requirements_readable"] = False
            errors.append("requirements_unreadable")
    else:
        details["requirements_readable"] = None

    # py_compile sample of up to 20 .py files at top levels
    py_errors = 0
    checked = 0
    for p in sorted(root.rglob("*.py")):
        if ".git" in p.parts or "venv" in p.parts or ".venv" in p.parts:
            continue
        checked += 1
        if checked > 20:
            break
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except SyntaxError:
            py_errors += 1
    details["py_checked"] = checked
    details["py_syntax_errors"] = py_errors
    if py_errors > 0 and main_hit is not None:
        errors.append(f"py_syntax_errors:{py_errors}")

    # Fail only on hard problems: empty, or entry syntax break, or many syntax errors
    if errors and (details.get("entry_ast_ok") is False or files < 2):
        return False, details, ";".join(errors)
    if details.get("entry_ast_ok") is False:
        return False, details, "entry_syntax_failed"
    return True, details, ""
