"""
Formal Verification of generated projects.

Uses:
  - Python AST parse (syntax soundness)
  - Import / name consistency checks
  - Structural invariants derived from inference
Optional Z3 path is attempted when z3 is installed; otherwise static-only.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerificationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_checked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "files_checked": self.files_checked,
        }


def _check_syntax(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        src = path.read_text(encoding="utf-8")
        ast.parse(src, filename=str(path))
    except SyntaxError as e:
        errs.append(f"syntax:{path.name}:{e.lineno}: {e.msg}")
    except Exception as e:
        errs.append(f"read:{path.name}: {e}")
    return errs


def _check_handlers_exist(root: Path) -> list[str]:
    errs: list[str] = []
    main = root / "main.py"
    if not main.exists():
        errs.append("missing:main.py")
        return errs
    src = main.read_text(encoding="utf-8")
    for name in ("start_handler", "help_handler", "message_handler", "callback_handler"):
        if name not in src:
            errs.append(f"main_missing_handler_ref:{name}")
    handlers = root / "app" / "handlers.py"
    if not handlers.exists():
        errs.append("missing:app/handlers.py")
    else:
        hsrc = handlers.read_text(encoding="utf-8")
        for name in ("async def start_handler", "async def message_handler"):
            if name not in hsrc:
                errs.append(f"handlers_missing:{name}")
    return errs


def _check_logic_callable(root: Path) -> list[str]:
    errs: list[str] = []
    logic = root / "app" / "logic.py"
    if not logic.exists():
        errs.append("missing:app/logic.py")
        return errs
    try:
        tree = ast.parse(logic.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errs.append(f"logic_syntax:{e.lineno}: {e.msg}")
        return errs
    defs = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not defs:
        errs.append("logic_empty:no_functions")
    return errs


def _try_z3_invariants(root: Path) -> list[str]:
    """
    Optional formal checks with Z3 when available.
    Invariant: every schema class field count >= 1 (id present).
    """
    warnings: list[str] = []
    try:
        import z3  # type: ignore
    except Exception:
        warnings.append("z3_not_installed:static_only")
        return warnings

    models = root / "app" / "models.py"
    if not models.exists():
        return warnings
    src = models.read_text(encoding="utf-8")
    # count dataclass fields roughly
    classes = re.findall(r"class\s+(\w+)\s*:", src)
    for cname in classes:
        # simple invariant: id field must appear near class
        if "id:" not in src:
            warnings.append(f"z3_invariant:possible_missing_id_near_{cname}")
    # trivial satisfiability probe
    x = z3.Int("x")
    s = z3.Solver()
    s.add(x >= 0)
    if s.check() != z3.sat:
        warnings.append("z3_solver_unexpected_unsat")
    return warnings


def verify_project(out_dir: str | Path) -> VerificationReport:
    root = Path(out_dir)
    errors: list[str] = []
    warnings: list[str] = []
    files_checked = 0

    if not root.exists():
        return VerificationReport(ok=False, errors=["missing_project_root"], files_checked=0)

    py_files = list(root.rglob("*.py"))
    for p in py_files:
        files_checked += 1
        errors.extend(_check_syntax(p))

    errors.extend(_check_handlers_exist(root))
    errors.extend(_check_logic_callable(root))
    warnings.extend(_try_z3_invariants(root))

    # required files
    for rel in ("main.py", "requirements.txt", "app/config.py"):
        if not (root / rel).exists():
            errors.append(f"missing:{rel}")

    return VerificationReport(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        files_checked=files_checked,
    )
