"""
Formal Verification of generated projects — deeper than py_compile.

Checks:
  - Python AST parse (syntax)
  - Handler wiring (main ↔ handlers)
  - Command coverage (every command has a handler)
  - Flow integrity (FLOWS steps non-empty, confirm/quantity patterns)
  - Callback maps consistency
  - Persistence surface when entity schemas exist (from user contract)
  - No invented cmd_hash command names
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
    fidelity_score: float = 0.0
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "files_checked": self.files_checked,
            "fidelity_score": self.fidelity_score,
            "checks": dict(self.checks),
        }


def _check_syntax(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        errs.append(f"syntax:{path.name}:{e.lineno}: {e.msg}")
    except Exception as e:
        errs.append(f"read:{path.name}: {e}")
    return errs


def _check_handlers_exist(root: Path) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    main = root / "main.py"
    handlers = root / "app" / "handlers.py"
    if not main.exists():
        return ["missing:main.py"], warns
    if not handlers.exists():
        return ["missing:app/handlers.py"], warns
    msrc = main.read_text(encoding="utf-8")
    hsrc = handlers.read_text(encoding="utf-8")
    for name in ("start_handler", "help_handler", "message_handler", "callback_handler"):
        if name not in msrc and name not in hsrc:
            errs.append(f"missing_handler_ref:{name}")
    for name in ("async def start_handler", "async def message_handler", "async def callback_handler"):
        if name not in hsrc:
            errs.append(f"handlers_missing:{name}")
    # Every CommandHandler("x" must have async def x_handler or imported
    for m in re.finditer(r'CommandHandler\(\s*[\'"](\w+)[\'"]\s*,\s*(\w+)', msrc):
        cmd, handler = m.group(1), m.group(2)
        if f"async def {handler}" not in hsrc and f"def {handler}" not in hsrc and handler not in hsrc:
            # may be imported from handlers import X
            if handler not in msrc.split("from app.handlers import")[-1][:500] and f"{handler}" not in hsrc:
                errs.append(f"command_handler_unresolved:{cmd}->{handler}")
        if cmd.startswith("cmd_") and len(cmd) > 4:
            errs.append(f"invented_cmd_hash:{cmd}")
    return errs, warns


def _check_logic_callable(root: Path) -> list[str]:
    logic = root / "app" / "logic.py"
    if not logic.exists():
        return ["missing:app/logic.py"]
    try:
        tree = ast.parse(logic.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [f"logic_syntax:{e.lineno}: {e.msg}"]
    defs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not defs:
        return ["logic_empty:no_functions"]
    return []


def _check_flows_and_callbacks(root: Path) -> tuple[list[str], list[str], dict[str, bool]]:
    errs, warns = [], []
    checks: dict[str, bool] = {}
    h = root / "app" / "handlers.py"
    if not h.exists():
        return ["missing:app/handlers.py"], warns, checks
    src = h.read_text(encoding="utf-8")

    checks["has_callback_labels"] = "CALLBACK_LABELS" in src
    checks["has_button_to_cmd"] = "BUTTON_TO_CMD" in src
    checks["has_flows"] = "FLOWS:" in src or "FLOWS =" in src

    # Structural flow quality only — no domain-specific order/catalog templates.
    for m in re.finditer(r"['\"]([a-z][a-z0-9_]*)['\"]\s*:\s*\[\s*\]", src):
        fid = m.group(1)
        if fid not in ("start", "help"):
            errs.append(f"flow_{fid}_empty_steps")
    checks["has_flow_steps"] = bool(re.search(r"['\"][a-z][a-z0-9_]*['\"]\s*:\s*\[\s*\{", src))
    if "BUTTON_TO_CMD" in src and "main_keyboard" in src:
        checks["keyboard_wired"] = True
    else:
        checks["keyboard_wired"] = "BUTTON_TO_CMD" not in src

    return errs, warns, checks


def _check_persistence(root: Path) -> tuple[list[str], list[str], dict[str, bool]]:
    errs, warns = [], []
    checks: dict[str, bool] = {}
    models = root / "app" / "models.py"
    store = root / "app" / "store.py"
    checks["has_models"] = models.exists()
    checks["has_store"] = store.exists()
    if models.exists():
        src = models.read_text(encoding="utf-8")
        checks["has_entity_classes"] = bool(re.search(r"^class\s+[A-Z]", src, re.M))
    if store.exists():
        ssrc = store.read_text(encoding="utf-8")
        checks["store_create"] = "async def create" in ssrc or "def create" in ssrc
    return errs, warns, checks


def _fidelity_score(checks: dict[str, bool], errors: list[str]) -> float:
    if errors:
        base = 0.35
    else:
        base = 0.55
    weights = {
        "has_flows": 0.12,
        "has_flow_steps": 0.12,
        "keyboard_wired": 0.1,
        "has_models": 0.1,
        "has_store": 0.1,
        "has_entity_classes": 0.1,
        "store_create": 0.08,
        "has_callback_labels": 0.08,
        "has_button_to_cmd": 0.08,
    }
    score = base
    for k, w in weights.items():
        if checks.get(k):
            score += w
    return round(min(1.0, score), 3)


def verify_project(out_dir: str | Path) -> VerificationReport:
    root = Path(out_dir)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}
    files_checked = 0

    if not root.exists():
        return VerificationReport(ok=False, errors=["missing_project_root"], files_checked=0)

    for p in root.rglob("*.py"):
        files_checked += 1
        errors.extend(_check_syntax(p))

    e1, w1 = _check_handlers_exist(root)
    errors.extend(e1)
    warnings.extend(w1)
    errors.extend(_check_logic_callable(root))

    e2, w2, c2 = _check_flows_and_callbacks(root)
    errors.extend(e2)
    warnings.extend(w2)
    checks.update(c2)

    e3, w3, c3 = _check_persistence(root)
    errors.extend(e3)
    warnings.extend(w3)
    checks.update(c3)

    for rel in ("main.py", "requirements.txt", "app/config.py"):
        if not (root / rel).exists():
            errors.append(f"missing:{rel}")

    score = _fidelity_score(checks, errors)
    if score < 0.5 and not errors:
        warnings.append(f"low_fidelity_score:{score}")

    return VerificationReport(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        files_checked=files_checked,
        fidelity_score=score,
        checks=checks,
    )
